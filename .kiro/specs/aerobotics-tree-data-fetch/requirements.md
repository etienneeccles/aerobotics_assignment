# Requirements Document

## Introduction

This feature replaces the existing JSON Placeholder demo client with a proper Aerobotics API client that fetches orchard survey data. The workflow involves three sequential API calls: retrieving surveys for an orchard, fetching tree survey summaries, and collecting all individual tree data with pagination support. The fetched data feeds into the downstream missing-tree detection pipeline.

## Glossary

- **API_Client**: The Python HTTP client class responsible for communicating with the Aerobotics REST API.
- **Orchard**: A farm area identified by a unique orchard_id, containing one or more surveys.
- **Survey**: A dated aerial survey of an orchard, identified by a unique survey_id. Contains metadata such as date, hectares, and polygon boundary.
- **Tree_Summary**: An aggregate summary for a survey containing tree_count, missing_tree_count, and statistical measures (average_area_m2, stddev_area_m2, average_ndre, stddev_ndre).
- **Tree_Record**: An individual tree observation from a survey, containing geolocation (lat, lng), vegetation indices (ndre, ndvi), physical measurements (volume, area), and grid position (row_index, tree_index).
- **Paginated_Response**: The Aerobotics API response format containing count, next, previous, and results fields. The next field contains the URL for the next page of results, or null if no more pages exist.
- **Workflow_Orchestrator**: The main module that coordinates the sequential API calls and aggregates results.
- **Missing_Tree_Detector**: The processing module that analyzes tree coordinates to identify gaps where trees are expected but missing.
- **Rotation_Matrix**: A 2x2 matrix used to rotate tree coordinates into axis-aligned space using PCA, enabling grid inference.
- **Grid_Spacing**: The inferred row and column spacing (dx, dy) between trees, computed from the median of coordinate differences.
- **Alpha_Shape**: A concave boundary polygon computed around the tree points to define the orchard's planted area. Falls back to convex hull if alpha shape fails.
- **Gap**: An expected grid position inside the orchard boundary that has no actual tree within a distance tolerance.
- **API_Server**: The REST web server (FastAPI) that exposes HTTP endpoints for querying orchard data, including missing tree locations.

## Requirements

### Requirement 1: API Client Setup

**User Story:** As a developer, I want a properly configured API client for the Aerobotics API, so that I can authenticate and make requests to the farming endpoints.

#### Acceptance Criteria

1. THE API_Client SHALL use `https://api.aerobotics.com` as the base URL.
2. THE API_Client SHALL accept an API authorization token at initialization and include it as a `Bearer` token in the `Authorization` header of every request.
3. THE API_Client SHALL use a persistent HTTP session for connection reuse across multiple requests.
4. WHEN a request is made, THE API_Client SHALL set a timeout of 30 seconds per request.
5. IF a network error or timeout occurs, THEN THE API_Client SHALL raise a descriptive exception containing the endpoint URL and error details.
6. IF the API returns an HTTP error status (4xx or 5xx), THEN THE API_Client SHALL raise a descriptive exception containing the status code and response body.

### Requirement 2: Fetch Surveys for an Orchard

**User Story:** As a developer, I want to retrieve all surveys for a given orchard, so that I can identify which survey data to process.

#### Acceptance Criteria

1. WHEN a valid orchard_id is provided, THE API_Client SHALL send a GET request to `/farming/surveys/` with the orchard_id as a query parameter.
2. WHEN the API returns a Paginated_Response of surveys, THE API_Client SHALL collect all survey results across all pages into a single list.
3. THE API_Client SHALL return each survey as a dictionary containing at minimum: id, orchard_id, date, hectares, and polygon fields.
4. IF the API returns zero surveys for the given orchard_id, THEN THE API_Client SHALL return an empty list.

### Requirement 3: Fetch Tree Survey Summary

**User Story:** As a developer, I want to retrieve the tree survey summary for a given survey, so that I can obtain aggregate tree statistics including the expected missing tree count.

#### Acceptance Criteria

1. WHEN a valid survey_id is provided, THE API_Client SHALL send a GET request to `/farming/surveys/{survey_id}/tree_survey_summaries/`.
2. THE API_Client SHALL return the Tree_Summary as a dictionary containing: survey_id, tree_count, missing_tree_count, average_area_m2, stddev_area_m2, average_ndre, and stddev_ndre.
3. IF the API returns no summary data for the given survey_id, THEN THE API_Client SHALL raise a descriptive exception indicating the survey has no summary available.

### Requirement 4: Fetch Individual Tree Data

**User Story:** As a developer, I want to retrieve all individual tree records for a survey, so that I can feed complete tree data into the missing-tree detection pipeline.

#### Acceptance Criteria

1. WHEN a valid survey_id is provided, THE API_Client SHALL send a GET request to `/farming/surveys/{survey_id}/tree_surveys/`.
2. WHEN the API returns a Paginated_Response of tree records, THE API_Client SHALL follow all pagination links and collect every Tree_Record into a single list.
3. THE API_Client SHALL return each Tree_Record as a dictionary containing: id, lat, lng, ndre, ndvi, volume, area, row_index, tree_index, and survey_id.
4. IF the API returns zero tree records for the given survey_id, THEN THE API_Client SHALL return an empty list.

### Requirement 5: Pagination Handling

**User Story:** As a developer, I want the API client to handle paginated responses transparently, so that I always receive complete datasets regardless of page size.

#### Acceptance Criteria

1. WHEN a Paginated_Response has a non-null `next` field, THE API_Client SHALL automatically fetch the next page using the URL in the `next` field.
2. THE API_Client SHALL continue fetching pages until the `next` field is null.
3. THE API_Client SHALL concatenate results from all pages into a single list preserving the order returned by the API.
4. WHEN paginating, THE API_Client SHALL use the same authorization headers and timeout settings for each page request.
5. IF a page request fails during pagination, THEN THE API_Client SHALL raise a descriptive exception indicating which page failed and the total records collected so far.

### Requirement 6: Data Fetching Workflow Orchestration

**User Story:** As a developer, I want a single entry point that executes the complete data-fetching workflow for an orchard, so that I can retrieve all necessary data with one function call.

#### Acceptance Criteria

1. WHEN an orchard_id is provided, THE Workflow_Orchestrator SHALL execute the three-step fetch sequence: retrieve surveys, fetch tree summary, and fetch all tree records.
2. WHEN multiple surveys exist for an orchard, THE Workflow_Orchestrator SHALL select only the most recent survey based on the `date` field.
3. THE Workflow_Orchestrator SHALL return a structured result containing the selected survey, its corresponding tree summary, and all tree records.
4. THE Workflow_Orchestrator SHALL log progress messages indicating which step is executing and how many records were fetched at each step.
5. IF any step in the workflow fails, THEN THE Workflow_Orchestrator SHALL report which step failed and any partial data collected from prior steps.

### Requirement 8: Extract Tree Coordinates

**User Story:** As a developer, I want to extract all tree lat/lng coordinates into an array of points, so that I can feed them into the downstream spatial analysis pipeline.

#### Acceptance Criteria

1. AFTER fetching all Tree_Records, THE Workflow_Orchestrator SHALL extract the `lat` and `lng` values from each record into a list of `(lat, lng)` tuples.
2. THE coordinate array SHALL preserve the same order as the fetched Tree_Records.
3. THE coordinate array SHALL be included in the workflow result under a `tree_points` key.
4. IF there are zero Tree_Records, THEN the `tree_points` array SHALL be empty.

### Requirement 9: Rotate Points to Axis-Aligned Space

**User Story:** As a developer, I want to rotate tree coordinates into axis-aligned space using PCA, so that the grid structure can be inferred from aligned rows and columns.

#### Acceptance Criteria

1. GIVEN a list of tree_points as an Nx2 numpy array, THE Missing_Tree_Detector SHALL compute the principal axis angle using PCA.
2. THE Missing_Tree_Detector SHALL apply a 2D rotation matrix to transform all points into axis-aligned space.
3. THE Missing_Tree_Detector SHALL return both the rotated points and the rotation matrix (for later inverse rotation).

### Requirement 10: Infer Grid Spacing

**User Story:** As a developer, I want to robustly infer the row and column spacing of the tree grid, so that I can generate expected tree positions.

#### Acceptance Criteria

1. GIVEN rotated tree coordinates, THE Missing_Tree_Detector SHALL compute the grid spacing (dx, dy) by taking the median of coordinate differences along each axis.
2. THE Missing_Tree_Detector SHALL filter out very small differences (less than 10% of the maximum difference) to remove floating-point noise before computing the median.

### Requirement 11: Build Candidate Expected Grid

**User Story:** As a developer, I want to generate a grid of expected tree positions covering the orchard extent, so that I can compare against actual tree locations.

#### Acceptance Criteria

1. GIVEN the rotated point extents and grid spacing (dx, dy), THE Missing_Tree_Detector SHALL generate a regular grid of candidate positions spanning from the minimum to maximum x and y coordinates.
2. THE candidate grid SHALL use the inferred dx and dy as step sizes.

### Requirement 12: Compute Orchard Boundary

**User Story:** As a developer, I want to compute a boundary polygon around the tree points, so that I only look for missing trees within the planted area.

#### Acceptance Criteria

1. THE Missing_Tree_Detector SHALL compute an alpha shape boundary around the rotated tree points using an automatically optimized alpha parameter.
2. IF the alpha shape is empty or produces a MultiPolygon, THEN THE Missing_Tree_Detector SHALL fall back to the convex hull of the points.
3. THE Missing_Tree_Detector SHALL apply a small buffer (0.4 × min(dx, dy)) to the boundary to avoid excluding edge trees.

### Requirement 13: Filter Grid Points and Detect Gaps

**User Story:** As a developer, I want to identify which expected grid positions are missing actual trees, so that I can report the gap locations.

#### Acceptance Criteria

1. THE Missing_Tree_Detector SHALL filter the candidate grid to only include points that fall inside the buffered boundary polygon.
2. THE Missing_Tree_Detector SHALL use a KDTree to find the nearest actual tree for each expected grid point.
3. IF the distance from an expected grid point to its nearest actual tree exceeds a tolerance of 0.3 × min(dx, dy), THEN that grid point SHALL be classified as a gap (missing tree).

### Requirement 14: Transform Gaps Back to Original Coordinates

**User Story:** As a developer, I want the missing tree locations reported in the original lat/lng coordinate space, so that they can be mapped and used downstream.

#### Acceptance Criteria

1. THE Missing_Tree_Detector SHALL apply the inverse rotation matrix to transform gap positions from rotated space back to original coordinates.
2. THE Missing_Tree_Detector SHALL return the gap locations as a list of `(lat, lng)` tuples.

### Requirement 15: Missing Tree Detection Pipeline

**User Story:** As a developer, I want a single function that runs the full missing tree detection pipeline on a list of tree points, so that I can integrate it into the workflow.

#### Acceptance Criteria

1. THE Missing_Tree_Detector SHALL accept a list of `(lat, lng)` tuples as input.
2. THE Missing_Tree_Detector SHALL execute the full pipeline: rotate → infer spacing → build grid → compute boundary → filter and detect gaps → inverse rotate.
3. THE Missing_Tree_Detector SHALL return the list of missing tree locations as `(lat, lng)` tuples.
4. THE Missing_Tree_Detector SHALL log the number of gaps found.
5. IF fewer than 3 tree points are provided, THEN THE Missing_Tree_Detector SHALL return an empty list (insufficient data for grid inference).

### Requirement 16: REST API Endpoint for Missing Trees

**User Story:** As an API consumer, I want to request missing tree locations for an orchard via a REST endpoint, so that I can integrate missing tree data into external applications without running the CLI workflow directly.

#### Acceptance Criteria

1. WHEN a GET request is made to `/orchards/{orchardId}/missing-trees`, THE API_Server SHALL execute the data-fetching workflow and missing tree detection pipeline for the given orchardId.
2. WHEN the pipeline completes successfully, THE API_Server SHALL return an HTTP 200 response with a JSON body containing an array of missing tree coordinates, where each element has `lat` and `lng` number fields.
3. WHEN the pipeline completes with zero missing trees, THE API_Server SHALL return an HTTP 200 response with an empty JSON array.
4. IF the orchardId has no surveys, THEN THE API_Server SHALL return an HTTP 404 response with a JSON error message indicating no surveys were found.
5. IF the Aerobotics upstream API returns an error during the workflow, THEN THE API_Server SHALL return an HTTP 502 response with a JSON error message describing the upstream failure.
6. IF the orchardId path parameter is not a valid integer, THEN THE API_Server SHALL return an HTTP 400 response with a JSON error message indicating an invalid orchard ID.

### Requirement 7: Console Output

**User Story:** As a developer, I want clear console output showing the fetched data summary, so that I can verify the workflow executed correctly.

#### Acceptance Criteria

1. WHEN the workflow completes, THE Workflow_Orchestrator SHALL display the number of surveys found for the orchard.
2. WHEN the workflow completes, THE Workflow_Orchestrator SHALL display the tree count and missing tree count from each Tree_Summary.
3. WHEN the workflow completes, THE Workflow_Orchestrator SHALL display the total number of individual Tree_Records fetched.
4. THE Workflow_Orchestrator SHALL use the Rich library for formatted console output.
