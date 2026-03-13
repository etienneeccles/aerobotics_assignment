# Design Document: Aerobotics Tree Data Fetch

## Overview

This design replaces the existing `JsonPlaceholderClient` with an `AeroboticsClient` that communicates with the Aerobotics farming API. The client handles authentication, pagination, and error reporting. A workflow orchestrator coordinates the three-step fetch sequence (surveys → tree summaries → tree records) and produces formatted console output via Rich.

A `Missing_Tree_Detector` module (`src/processing.py`) takes the extracted tree coordinates and runs a spatial analysis pipeline to identify gaps where trees are expected but missing. The pipeline uses PCA-based rotation to align the orchard grid, infers row/column spacing, generates expected positions, computes an alpha-shape boundary, and detects gaps via KDTree nearest-neighbor queries.

A FastAPI-based REST server (`src/server.py`) exposes a `GET /orchards/{orchardId}/missing-trees` endpoint that internally calls the existing workflow orchestrator and returns the detected missing tree coordinates as a JSON array of `{lat, lng}` objects.

The design prioritizes simplicity: a single client class with methods per endpoint, a generic pagination helper, a thin orchestration layer in `main.py`, a stateless processing module with pure functions for each pipeline step, and a lightweight REST layer that delegates to the existing workflow.

## Architecture

```mermaid
graph TD
    S[server.py - FastAPI REST Server] --> A
    S --> |GET /orchards/id/missing-trees| R[JSON Response]
    A[main.py - Workflow Orchestrator] --> B[AeroboticsClient]
    B --> C[GET /farming/surveys/]
    B --> D[GET /farming/surveys/{id}/tree_survey_summaries/]
    B --> E[GET /farming/surveys/{id}/tree_surveys/]
    B --> F[_get_paginated - pagination helper]
    F --> C
    F --> E
    A --> G[Rich Console Output]
    A --> H[Missing_Tree_Detector]
    H --> H1[rotate_points - PCA rotation]
    H --> H2[infer_spacing - median grid spacing]
    H --> H3[build_candidate_grid - expected positions]
    H --> H4[compute_boundary - alpha shape + fallback]
    H --> H5[detect_gaps - KDTree nearest neighbor]
    H --> H6[inverse_rotate - back to lat/lng]
```

**Flow:**
1. `server.py` receives `GET /orchards/{orchardId}/missing-trees`
2. Creates an `AeroboticsClient` with the API token from environment
3. Calls `fetch_orchard_data(client, orchardId)` from `main.py`
4. Extracts `missing_trees` from the result
5. Returns JSON array of `{lat, lng}` objects

**CLI Flow (unchanged):**
1. `main.py` creates an `AeroboticsClient` with an API token
2. Calls `get_surveys(orchard_id)` — uses pagination helper
3. Selects the most recent survey by sorting on the `date` field
4. Calls `get_tree_summary(survey_id)` for the selected survey — single response
5. Calls `get_tree_records(survey_id)` for the selected survey — uses pagination helper
6. Extracts `[lat, lng]` pairs from tree records into a `tree_points` list
7. Passes `tree_points` to `Missing_Tree_Detector.detect_missing_trees()` pipeline
8. Aggregates results and prints summary via Rich

**Missing Tree Detection Pipeline Flow:**
```
tree_points → rotate_points (PCA) → infer_spacing (median diffs)
  → build_candidate_grid → compute_boundary (alpha shape)
  → filter_and_detect_gaps (KDTree) → inverse_rotate → gap locations
```

## Components and Interfaces

### AeroboticsClient (`src/api_client.py`)

Replaces `JsonPlaceholderClient`. Responsible for all HTTP communication with the Aerobotics API.

```python
class AeroboticsClient:
    BASE_URL = "https://api.aerobotics.com"
    TIMEOUT = 30

    def __init__(self, api_token: str, base_url: str = BASE_URL):
        """Initialize with Bearer token. Creates a persistent requests.Session."""

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """
        Send GET request to endpoint. Raises AeroboticsAPIError on HTTP errors
        or network failures. Returns parsed JSON.
        """

    def _get_paginated(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """
        Fetch all pages from a paginated endpoint. Follows 'next' URLs until null.
        Returns concatenated results list. Raises AeroboticsAPIError with partial
        data context on failure.
        """

    def get_surveys(self, orchard_id: int) -> list[dict]:
        """Fetch all surveys for an orchard. Returns list of survey dicts."""

    def get_tree_summary(self, survey_id: int) -> dict:
        """Fetch tree survey summary. Raises if no summary available."""

    def get_tree_records(self, survey_id: int) -> list[dict]:
        """Fetch all individual tree records for a survey. Handles pagination."""
```

### AeroboticsAPIError (`src/api_client.py`)

Custom exception for API errors.

```python
class AeroboticsAPIError(Exception):
    def __init__(self, message: str, status_code: int | None = None,
                 endpoint: str | None = None, response_body: str | None = None):
        """Descriptive error with context about what failed."""
```

### API Server (`src/server.py`)

FastAPI application exposing the REST endpoint. Delegates to the existing workflow orchestrator.

```python
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()

class Coordinate(BaseModel):
    lat: float
    lng: float

@app.get("/orchards/{orchard_id}/missing-trees", response_model=list[Coordinate])
def get_missing_trees(orchard_id: int) -> list[Coordinate]:
    """
    Execute the data-fetching workflow for the given orchard and return
    missing tree coordinates as a JSON array of {lat, lng} objects.

    Returns:
        200: List of {lat, lng} coordinates
        400: Invalid orchard ID (handled by FastAPI path param validation)
        404: No surveys found for the orchard
        502: Upstream Aerobotics API error
    """
```

### Workflow Orchestrator (`src/main.py`)

Coordinates the fetch sequence, runs the missing tree detection pipeline, and produces console output.

```python
def fetch_orchard_data(client: AeroboticsClient, orchard_id: int) -> dict:
    """
    Execute the complete data-fetching workflow:
    1. Fetch all surveys for orchard_id
    2. Select the most recent survey by date
    3. Fetch tree summary for the selected survey
    4. Fetch all tree records for the selected survey
    5. Extract [lat, lng] pairs into tree_points
    6. Run missing tree detection pipeline on tree_points
    Returns: {
        "orchard_id": int,
        "survey": dict,
        "tree_summary": dict,
        "tree_records": list[dict],
        "tree_points": list[tuple[float, float]],
        "missing_trees": list[tuple[float, float]]
    }
    """

def print_results(results: dict) -> None:
    """Print formatted summary using Rich, including missing tree count."""

def main() -> None:
    """Entry point: read token, create client, run workflow, print results."""
```

### Missing_Tree_Detector (`src/processing.py`)

Stateless module with pure functions for each step of the missing tree detection pipeline. Refactored from the existing `src/procesing.py` script.

```python
import numpy as np
from numpy.typing import NDArray
from sklearn.decomposition import PCA
from scipy.spatial import KDTree
import alphashape
from shapely.geometry import Point, MultiPoint

def rotate_points(points: NDArray, angle: float) -> tuple[NDArray, NDArray]:
    """
    Apply 2D rotation by `angle` radians to Nx2 array of points.
    Returns (rotated_points, rotation_matrix).
    Rotation preserves pairwise distances (isometry).
    """

def compute_pca_angle(points: NDArray) -> float:
    """
    Compute the principal axis angle from an Nx2 array using PCA.
    Returns the angle (radians) to rotate points into axis-aligned space.
    """

def infer_spacing(coords: NDArray) -> float:
    """
    Infer grid spacing along one axis from sorted unique coordinate values.
    Computes median of diffs after filtering out diffs < 10% of max diff.
    """

def infer_grid_spacing(rotated: NDArray) -> tuple[float, float]:
    """
    Infer (dx, dy) grid spacing from rotated Nx2 points.
    Rounds to 6 decimal places, then calls infer_spacing per axis.
    """

def build_candidate_grid(
    x_min: float, x_max: float,
    y_min: float, y_max: float,
    dx: float, dy: float
) -> NDArray:
    """
    Generate a regular Mx2 grid of candidate positions spanning
    [x_min, x_max] × [y_min, y_max] with step sizes dx, dy.
    """

def compute_boundary(
    rotated: NDArray, dx: float, dy: float
) -> 'shapely.geometry.base.BaseGeometry':
    """
    Compute alpha shape boundary around rotated points.
    Falls back to convex hull if alpha shape is empty or MultiPolygon.
    Applies buffer of 0.4 * min(dx, dy).
    """

def filter_and_detect_gaps(
    candidate_grid: NDArray,
    rotated: NDArray,
    boundary: 'shapely.geometry.base.BaseGeometry',
    dx: float, dy: float
) -> NDArray:
    """
    Filter candidate grid to points inside boundary.
    Use KDTree to find nearest actual tree for each expected point.
    Points with nearest-tree distance > 0.3 * min(dx, dy) are gaps.
    Returns Kx2 array of gap positions in rotated space.
    """

def inverse_rotate(points: NDArray, rotation_matrix: NDArray) -> NDArray:
    """
    Apply inverse rotation (R^T) to transform points back to original space.
    Returns Nx2 array.
    """

def detect_missing_trees(
    tree_points: list[tuple[float, float]]
) -> list[tuple[float, float]]:
    """
    Full pipeline: rotate → infer spacing → build grid → compute boundary
    → filter and detect gaps → inverse rotate.
    Returns list of (lat, lng) gap locations.
    Returns empty list if fewer than 3 points provided.
    Logs the number of gaps found.
    """
```

## Data Models

The API returns JSON that we consume as plain dictionaries. Below are the expected shapes.

### Survey
```python
{
    "id": 25319,
    "orchard_id": 216269,
    "date": "2019-05-03",
    "hectares": 2.242,
    "polygon": "18.825688...-32.327414... ..."
}
```

### Tree Summary
```python
{
    "survey_id": 25319,
    "tree_count": 508,
    "missing_tree_count": 4,
    "average_area_m2": 21.212,
    "stddev_area_m2": 3.873,
    "average_ndre": 0.554,
    "stddev_ndre": 0.036
}
```

### Tree Record
```python
{
    "id": 54733434,
    "lat": -32.3279643,
    "lng": 18.826872,
    "ndre": 0.557,
    "ndvi": 0.872,
    "volume": 50.558,
    "area": 22.667,
    "row_index": None,
    "tree_index": None,
    "survey_id": 25319
}
```

### Paginated Response Envelope
```python
{
    "count": 508,
    "next": "https://api.aerobotics.com/farming/surveys/25319/tree_surveys/?limit=2&offset=2",
    "previous": None,
    "results": [...]
}
```

### Workflow Result
```python
{
    "orchard_id": 216269,
    "survey": { ... },            # The most recent Survey dict
    "tree_summary": { ... },      # Tree Summary for the selected survey
    "tree_records": [ ... ],      # List of Tree Record dicts
    "tree_points": [              # Extracted (lat, lng) pairs
        (-32.3279643, 18.826872),
        (-32.3281234, 18.826901),
        ...
    ],
    "missing_trees": [            # Detected gap locations (lat, lng)
        (-32.3280100, 18.826850),
        ...
    ]
}
```

### Pipeline Intermediate Data

```python
# rotate_points output
rotated: NDArray  # Nx2 float64, axis-aligned coordinates
rotation_matrix: NDArray  # 2x2 float64

# infer_grid_spacing output
dx: float  # column spacing
dy: float  # row spacing

# build_candidate_grid output
candidate_grid: NDArray  # Mx2 float64, all expected positions

# compute_boundary output
boundary: shapely.geometry.Polygon  # buffered alpha shape or convex hull

# filter_and_detect_gaps output
gaps_rotated: NDArray  # Kx2 float64, gap positions in rotated space

# inverse_rotate output
gaps_original: NDArray  # Kx2 float64, gap positions in original lat/lng space
```

### API Response: Missing Trees Endpoint

```
GET /orchards/{orchardId}/missing-trees

200 OK:
[
    {"lat": -32.3280100, "lng": 18.826850},
    {"lat": -32.3281500, "lng": 18.826920}
]

200 OK (no missing trees):
[]

404 Not Found:
{"detail": "No surveys found for orchard 999999"}

502 Bad Gateway:
{"detail": "Upstream API error: HTTP 500 error for ..."}

400 Bad Request (non-integer orchardId — handled by FastAPI):
{"detail": [{"type": "int_parsing", ...}]}
```


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system — essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: Bearer token on all requests

*For any* request made by the API_Client (including pagination follow-up requests), the HTTP `Authorization` header SHALL contain `Bearer {token}` where `{token}` is the token provided at initialization.

**Validates: Requirements 1.2, 5.4**

### Property 2: Pagination collects all results in order

*For any* paginated endpoint returning N pages with a total of M items, calling the pagination helper SHALL return a single list of exactly M items, where the items appear in the same order as they would if the pages were concatenated sequentially (page 1 results, then page 2 results, ..., then page N results).

**Validates: Requirements 2.2, 4.2, 5.1, 5.2, 5.3**

### Property 3: HTTP errors produce descriptive exceptions

*For any* HTTP response with a status code in the 4xx or 5xx range, the API_Client SHALL raise an `AeroboticsAPIError` whose message contains both the numeric status code and the response body text.

**Validates: Requirements 1.6**

### Property 4: Latest survey selection

*For any* orchard with N surveys (N ≥ 1) having distinct dates, the Workflow_Orchestrator SHALL select the survey whose `date` field is the maximum among all surveys returned.

**Validates: Requirements 6.2**

### Property 5: Tree points extraction preserves records

*For any* list of Tree_Records, the `tree_points` array in the workflow result SHALL have the same length as the tree records list, and `tree_points[i]` SHALL equal `(tree_records[i]["lat"], tree_records[i]["lng"])` for every valid index `i`.

**Validates: Requirements 8.1, 8.2, 8.3, 8.4**

### Property 6: Rotation preserves pairwise distances (isometry)

*For any* Nx2 array of points and any rotation angle, the Euclidean distance between every pair of points before rotation SHALL equal the Euclidean distance between the corresponding pair after rotation, within floating-point tolerance.

**Validates: Requirements 9.2**

### Property 7: Rotation round-trip (rotate then inverse ≈ identity)

*For any* Nx2 array of points, rotating the points by an angle and then applying the inverse rotation (R^T) SHALL produce points equal to the originals within floating-point tolerance.

**Validates: Requirements 9.2, 9.3, 14.1**

### Property 8: Regular grid spacing inference matches true spacing

*For any* regular grid with known spacing (dx_true, dy_true), the inferred spacing (dx, dy) from `infer_grid_spacing` SHALL equal (dx_true, dy_true) within floating-point tolerance.

**Validates: Requirements 10.1, 10.2**

### Property 9: Generated grid covers full extent with correct step sizes

*For any* bounding box [x_min, x_max] × [y_min, y_max] and positive step sizes (dx, dy), the candidate grid from `build_candidate_grid` SHALL have its minimum x ≥ x_min, maximum x ≤ x_max + dx, minimum y ≥ y_min, maximum y ≤ y_max + dy, and consecutive points along each axis SHALL differ by exactly dx or dy.

**Validates: Requirements 11.1**

### Property 10: Boundary contains all original tree points

*For any* set of tree points (N ≥ 3), the buffered boundary polygon returned by `compute_boundary` SHALL contain every input point.

**Validates: Requirements 12.1, 12.2, 12.3**

### Property 11: Every reported gap has no actual tree within tolerance

*For any* set of actual tree positions and detected gap positions, the distance from each gap to its nearest actual tree SHALL exceed the tolerance threshold (0.3 × min(dx, dy)).

**Validates: Requirements 13.1, 13.2, 13.3**

### Property 12: End-to-end pipeline detects removed trees from synthetic grid

*For any* regular grid of points with some points removed, running `detect_missing_trees` on the remaining points SHALL report gap locations that are close (within tolerance) to the removed points.

**Validates: Requirements 15.1, 15.2, 15.3**

### Property 13: API response shape matches coordinate contract

*For any* list of missing tree coordinate tuples (including an empty list) returned by the detection pipeline, the REST endpoint SHALL return an HTTP 200 JSON array where every element is an object with exactly `lat` (number) and `lng` (number) fields, and the array length equals the number of input tuples.

**Validates: Requirements 16.2, 16.3**

### Property 14: Upstream API errors map to HTTP 502

*For any* `AeroboticsAPIError` raised during the workflow (with any message, status code, or endpoint), the REST endpoint SHALL return an HTTP 502 response whose JSON body contains a `detail` field describing the upstream failure.

**Validates: Requirements 16.5**

## Error Handling

| Scenario | Behavior |
|---|---|
| Network error / timeout | `AeroboticsAPIError` raised with endpoint URL and error message |
| HTTP 4xx/5xx | `AeroboticsAPIError` raised with status code and response body |
| Empty survey list | Return empty list, no exception |
| No tree summary for survey | `AeroboticsAPIError` raised indicating missing summary |
| Pagination failure mid-stream | `AeroboticsAPIError` raised with page number and count of records collected so far |
| Workflow step failure | Exception propagated with context about which step failed; partial data from prior steps included in error context |
| Single survey with no date field | Orchestrator treats missing date as earliest, still selects the survey with the latest parseable date |
| Fewer than 3 tree points | `detect_missing_trees` returns empty list immediately (insufficient data for PCA/grid inference) |
| Alpha shape fails (empty or MultiPolygon) | Falls back to convex hull of points |
| Alpha shape optimization fails | Catches exception, falls back to convex hull |
| All candidate grid points outside boundary | Returns empty gap list (no expected positions inside orchard) |
| Zero gaps detected | Returns empty list, logs "0 gaps found" |
| REST endpoint: no surveys for orchard | Returns HTTP 404 with descriptive JSON error message |
| REST endpoint: upstream Aerobotics API failure | Returns HTTP 502 with JSON error describing the upstream failure |
| REST endpoint: invalid orchardId (non-integer) | FastAPI returns HTTP 422 validation error automatically |

All exceptions use the custom `AeroboticsAPIError` class to provide consistent, descriptive error messages. The `requests` library's `ConnectionError`, `Timeout`, and `HTTPError` exceptions are caught and wrapped.

## Testing Strategy

### Unit Tests

Unit tests use `unittest.mock` to patch `requests.Session` and verify:
- Correct endpoint URLs and query parameters for each method
- Bearer token header presence
- Timeout parameter passed to every request
- Correct handling of empty responses (edge cases from 2.4, 4.4)
- Exception raising for missing tree summary (3.3)
- Exception content for network errors (1.5) and HTTP errors (1.6)
- Pagination failure mid-stream error message (5.5)
- Workflow orchestration sequence and result structure (6.1, 6.3)
- Latest survey selection when multiple surveys exist (6.2)
- Tree points extraction from tree records (8.1, 8.2, 8.3)
- Empty tree records produce empty tree_points (8.4)
- Workflow error reporting with partial data (6.5)

Unit tests for Missing_Tree_Detector (`src/processing.py`):
- `compute_pca_angle` returns a float angle for a simple known point set
- `infer_spacing` filters out small diffs and returns median of remaining
- `build_candidate_grid` produces correct grid dimensions for known inputs
- `compute_boundary` falls back to convex hull when alpha shape fails (collinear points)
- `compute_boundary` applies buffer of correct size
- `filter_and_detect_gaps` returns empty array when all expected points have nearby trees
- `detect_missing_trees` returns empty list for fewer than 3 points (edge case from 15.5)
- `detect_missing_trees` returns empty list for exactly 0 points
- `inverse_rotate` with identity matrix returns original points

Unit tests for API Server (`src/server.py`):
- `GET /orchards/{orchardId}/missing-trees` calls `fetch_orchard_data` with correct orchardId
- Returns 200 with JSON array of `{lat, lng}` objects on success
- Returns 200 with empty array when no missing trees detected
- Returns 404 when no surveys found for the orchard
- Returns 502 when upstream AeroboticsAPIError is raised
- Returns 422 when orchardId is not a valid integer (FastAPI validation)

### Property-Based Tests

Property-based tests use the `hypothesis` library with `hypothesis.extra.numpy` for array generation (minimum 100 examples per test).

Each property test generates randomized inputs and verifies the universal property holds:

- **Feature: aerobotics-tree-data-fetch, Property 1: Bearer token on all requests** — Generate random tokens and random sequences of API calls, verify every mocked request carries the correct Authorization header.
- **Feature: aerobotics-tree-data-fetch, Property 2: Pagination collects all results in order** — Generate random page counts (1–20) with random items per page, mock the paginated responses, verify the returned list equals the concatenation of all page results in order.
- **Feature: aerobotics-tree-data-fetch, Property 3: HTTP errors produce descriptive exceptions** — Generate random 4xx/5xx status codes and random response bodies, verify the raised exception message contains both.
- **Feature: aerobotics-tree-data-fetch, Property 4: Latest survey selection** — Generate random lists of surveys (1–10) with random dates, run selection logic, verify the selected survey has the maximum date.
- **Feature: aerobotics-tree-data-fetch, Property 5: Tree points extraction preserves records** — Generate random lists of tree records with random lat/lng values, run extraction, verify tree_points[i] == (tree_records[i]["lat"], tree_records[i]["lng"]) for all i, and length matches.
- **Feature: aerobotics-tree-data-fetch, Property 6: Rotation preserves pairwise distances** — Generate random Nx2 arrays and random angles, rotate, verify all pairwise distances are preserved within tolerance.
- **Feature: aerobotics-tree-data-fetch, Property 7: Rotation round-trip** — Generate random Nx2 arrays and random angles, rotate then inverse-rotate, verify result ≈ original within tolerance.
- **Feature: aerobotics-tree-data-fetch, Property 8: Regular grid spacing inference** — Generate random regular grids with known (dx, dy), run `infer_grid_spacing`, verify inferred spacing matches true spacing.
- **Feature: aerobotics-tree-data-fetch, Property 9: Generated grid covers full extent** — Generate random bounding boxes and step sizes, run `build_candidate_grid`, verify coverage and step size invariants.
- **Feature: aerobotics-tree-data-fetch, Property 10: Boundary contains all original points** — Generate random point clouds (N ≥ 3), compute boundary, verify every input point is contained.
- **Feature: aerobotics-tree-data-fetch, Property 11: Every gap has no nearby actual tree** — Generate random tree positions and run gap detection, verify each gap's nearest-tree distance exceeds tolerance.
- **Feature: aerobotics-tree-data-fetch, Property 12: End-to-end pipeline detects removed trees** — Generate regular grids, remove random subset, run `detect_missing_trees`, verify reported gaps are near removed points.
- **Feature: aerobotics-tree-data-fetch, Property 13: API response shape matches coordinate contract** — Generate random lists of (lat, lng) tuples (including empty), mock the workflow to return them, call the endpoint via FastAPI TestClient, verify response is 200 with correct JSON array shape.
- **Feature: aerobotics-tree-data-fetch, Property 14: Upstream API errors map to HTTP 502** — Generate random AeroboticsAPIError instances (random messages, status codes), mock the workflow to raise them, call the endpoint, verify 502 response with detail field.

### Test Dependencies

Add to `requirements.txt` (dev dependencies):
- `pytest>=7.0.0`
- `hypothesis>=6.0.0`
- `numpy>=1.24.0`
- `pandas>=2.0.0`
- `scipy>=1.10.0`
- `scikit-learn>=1.2.0`
- `alphashape>=1.3.0`
- `shapely>=2.0.0`
- `fastapi>=0.100.0`
- `uvicorn>=0.23.0`
- `httpx>=0.24.0` (for FastAPI TestClient)
