# Implementation Plan: Aerobotics Tree Data Fetch

## Overview

Replace the existing `JsonPlaceholderClient` with an `AeroboticsClient` that fetches orchard survey data from the Aerobotics API. Implementation proceeds bottom-up: custom exception, API client with pagination, workflow orchestrator, then main entry point with Rich output.

## Tasks

- [x] 1. Implement AeroboticsAPIError and AeroboticsClient core
  - [x] 1.1 Create `AeroboticsAPIError` exception class and `AeroboticsClient` with `__init__` and `_get` methods in `src/api_client.py`
    - Remove the `JsonPlaceholderClient` class entirely
    - `AeroboticsAPIError` stores message, status_code, endpoint, and response_body
    - `__init__` accepts `api_token` and optional `base_url`, creates `requests.Session` with `Authorization: Bearer {token}` header
    - `_get` sends GET with 30s timeout, catches `requests.RequestException` and `HTTPError`, wraps in `AeroboticsAPIError`
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_

  - [ ]* 1.2 Write property test: HTTP errors produce descriptive exceptions
    - **Property 3: HTTP errors produce descriptive exceptions**
    - Generate random 4xx/5xx status codes and response bodies, mock `requests.Session.get`, verify `AeroboticsAPIError` contains status code and body
    - **Validates: Requirements 1.6**

  - [ ]* 1.3 Write unit tests for AeroboticsClient core
    - Test Bearer token is set in session headers
    - Test base URL defaults to `https://api.aerobotics.com`
    - Test timeout of 30s is passed to requests
    - Test network error raises `AeroboticsAPIError` with endpoint URL
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 2. Implement pagination and endpoint methods
  - [x] 2.1 Add `_get_paginated` method to `AeroboticsClient`
    - Calls `_get` for initial page, follows `next` URLs until null
    - Concatenates all `results` lists in order
    - On failure mid-pagination, raises `AeroboticsAPIError` with page number and records collected so far
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 2.2 Add `get_surveys`, `get_tree_summary`, and `get_tree_records` methods
    - `get_surveys(orchard_id)` calls `_get_paginated` on `/farming/surveys/` with `orchard_id` param
    - `get_tree_summary(survey_id)` calls `_get` on `/farming/surveys/{survey_id}/tree_survey_summaries/`, raises if empty
    - `get_tree_records(survey_id)` calls `_get_paginated` on `/farming/surveys/{survey_id}/tree_surveys/`
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4_

  - [ ]* 2.3 Write property test: Pagination collects all results in order
    - **Property 2: Pagination collects all results in order**
    - Generate random page counts (1–20) with random items per page, mock paginated responses, verify returned list equals concatenation of all pages
    - **Validates: Requirements 2.2, 4.2, 5.1, 5.2, 5.3**

  - [ ]* 2.4 Write property test: Bearer token on all requests
    - **Property 1: Bearer token on all requests**
    - Generate random tokens and multi-page responses, verify every mocked request carries correct Authorization header
    - **Validates: Requirements 1.2, 5.4**

  - [ ]* 2.5 Write unit tests for endpoint methods
    - Test `get_surveys` sends correct URL and params, returns list
    - Test `get_surveys` returns empty list for zero results
    - Test `get_tree_summary` returns dict with expected fields
    - Test `get_tree_summary` raises on empty response
    - Test `get_tree_records` handles multi-page response
    - Test `get_tree_records` returns empty list for zero results
    - Test pagination failure mid-stream includes page info
    - _Requirements: 2.1, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.3, 4.4, 5.5_

- [x] 3. Checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement workflow orchestrator and main entry point
  - [x] 4.1 Implement `fetch_orchard_data` function in `src/main.py`
    - Accepts `AeroboticsClient` and `orchard_id`
    - Calls `get_surveys`, then for each survey calls `get_tree_summary` and `get_tree_records`
    - Returns structured dict with orchard_id and list of survey data
    - Logs progress via Rich console
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [x] 4.2 Implement `print_results` and update `main()` in `src/main.py`
    - `print_results` displays survey count, tree count, missing tree count, and total tree records using Rich
    - `main()` reads API token (from env var or argument), creates `AeroboticsClient`, calls `fetch_orchard_data`, calls `print_results`
    - Remove all JSON Placeholder demo code
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 4.3 Write property test: Orchestrator processes all surveys
    - **Property 4: Orchestrator processes all surveys**
    - Generate random survey counts (1–10), mock all API responses, verify result contains one entry per survey
    - **Validates: Requirements 6.2**

  - [ ]* 4.4 Write unit tests for workflow orchestrator
    - Test three-step sequence is called in order
    - Test result structure matches expected shape
    - Test error in step 2 reports which step failed
    - _Requirements: 6.1, 6.3, 6.5_

- [x] 5. Update dependencies
  - [x] 5.1 Update `requirements.txt` with test dependencies
    - Add `pytest>=7.0.0` and `hypothesis>=6.0.0`
    - _Requirements: Testing Strategy_

- [x] 7. Implement latest survey selection and tree_points extraction
  - [x] 7.1 Update `fetch_orchard_data` in `src/main.py` to select only the most recent survey
    - After fetching surveys, sort by `date` field and pick the one with the latest date
    - Only fetch tree summary and tree records for the selected survey (not all surveys)
    - Update result structure: replace `surveys` list with single `survey`, `tree_summary`, `tree_records` keys
    - _Requirements: 6.2, 6.3_

  - [x] 7.2 Add tree_points extraction to `fetch_orchard_data`
    - After fetching tree records, extract `(lat, lng)` tuples from each record
    - Store as list of `(lat, lng)` tuples under `tree_points` key in result dict
    - Preserve same order as tree records; empty list if no records
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x] 7.3 Update `print_results` to handle new result structure
    - Adapt from multi-survey display to single-survey display
    - Display tree_points count in output
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 7.4 Write property test: Latest survey selection
    - **Property 4: Latest survey selection**
    - Generate random lists of surveys (1–10) with random dates, verify selected survey has the maximum date
    - **Validates: Requirements 6.2**

  - [ ]* 7.5 Write property test: Tree points extraction preserves records
    - **Property 5: Tree points extraction preserves records**
    - Generate random tree records with random lat/lng, verify tree_points[i] == (tree_records[i]["lat"], tree_records[i]["lng"]) for all i
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4**

- [ ] 8. Final checkpoint
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 9. Implement Missing_Tree_Detector core functions (rotation and spacing)
  - [x] 9.1 Create `src/processing.py` with `rotate_points`, `compute_pca_angle`, `infer_spacing`, and `infer_grid_spacing`
    - Rename/refactor from existing `src/procesing.py` script into proper functions
    - `compute_pca_angle(points)` fits PCA on Nx2 array, returns angle in radians
    - `rotate_points(points, angle)` applies 2D rotation matrix, returns (rotated, R)
    - `infer_spacing(coords)` sorts unique values, diffs, filters < 10% of max, returns median
    - `infer_grid_spacing(rotated)` rounds to 6 decimals, calls `infer_spacing` per axis, returns (dx, dy)
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2_

  - [ ]* 9.2 Write property test: Rotation preserves pairwise distances
    - **Property 6: Rotation preserves pairwise distances (isometry)**
    - Generate random Nx2 arrays and angles, verify all pairwise distances preserved within tolerance
    - **Validates: Requirements 9.2**

  - [ ]* 9.3 Write property test: Rotation round-trip
    - **Property 7: Rotation round-trip (rotate then inverse ≈ identity)**
    - Generate random Nx2 arrays and angles, rotate then inverse-rotate, verify ≈ original
    - **Validates: Requirements 9.2, 9.3, 14.1**

  - [ ]* 9.4 Write property test: Regular grid spacing inference
    - **Property 8: Regular grid spacing inference matches true spacing**
    - Generate random regular grids with known (dx, dy), verify inferred spacing matches
    - **Validates: Requirements 10.1, 10.2**

  - [ ]* 9.5 Write unit tests for rotation and spacing functions
    - Test `compute_pca_angle` with a known axis-aligned point set
    - Test `infer_spacing` filters small diffs correctly
    - Test `infer_grid_spacing` on a simple 3x3 grid
    - Test `rotate_points` with 90-degree rotation on known points
    - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2_

- [ ] 10. Implement grid generation, boundary, and gap detection
  - [x] 10.1 Add `build_candidate_grid`, `compute_boundary`, `filter_and_detect_gaps`, and `inverse_rotate` to `src/processing.py`
    - `build_candidate_grid(x_min, x_max, y_min, y_max, dx, dy)` uses `np.arange` to generate Mx2 grid
    - `compute_boundary(rotated, dx, dy)` uses `alphashape.optimizealpha` + `alphashape.alphashape`, falls back to convex hull, applies buffer
    - `filter_and_detect_gaps(candidate_grid, rotated, boundary, dx, dy)` filters by boundary containment, uses KDTree, returns gaps where distance > 0.3 * min(dx, dy)
    - `inverse_rotate(points, R)` applies R^T to transform back
    - _Requirements: 11.1, 12.1, 12.2, 12.3, 13.1, 13.2, 13.3, 14.1, 14.2_

  - [ ]* 10.2 Write property test: Generated grid covers full extent
    - **Property 9: Generated grid covers full extent with correct step sizes**
    - Generate random bounding boxes and step sizes, verify coverage and step invariants
    - **Validates: Requirements 11.1**

  - [ ]* 10.3 Write property test: Boundary contains all original points
    - **Property 10: Boundary contains all original tree points**
    - Generate random point clouds (N ≥ 3), compute boundary, verify containment
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [ ]* 10.4 Write property test: Every gap has no nearby actual tree
    - **Property 11: Every reported gap has no actual tree within tolerance**
    - Generate random tree positions, run gap detection, verify distance invariant
    - **Validates: Requirements 13.1, 13.2, 13.3**

  - [ ]* 10.5 Write unit tests for grid, boundary, and gap detection
    - Test `build_candidate_grid` dimensions for known inputs
    - Test `compute_boundary` falls back to convex hull for collinear points
    - Test `filter_and_detect_gaps` returns empty when all positions have nearby trees
    - Test `inverse_rotate` with identity matrix
    - _Requirements: 11.1, 12.1, 12.2, 13.1, 13.3, 14.1_

- [ ] 11. Checkpoint - Ensure processing tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement end-to-end pipeline and integrate with workflow
  - [x] 12.1 Add `detect_missing_trees` pipeline function to `src/processing.py`
    - Accepts `list[tuple[float, float]]`, returns `list[tuple[float, float]]`
    - Returns empty list if fewer than 3 points
    - Chains: compute_pca_angle → rotate_points → infer_grid_spacing → build_candidate_grid → compute_boundary → filter_and_detect_gaps → inverse_rotate
    - Logs number of gaps found
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5_

  - [x] 12.2 Integrate `detect_missing_trees` into `fetch_orchard_data` in `src/main.py`
    - After extracting tree_points, call `detect_missing_trees(tree_points)`
    - Store result under `missing_trees` key in result dict
    - Update `print_results` to display missing tree count from detection
    - _Requirements: 15.2, 15.3, 7.1, 7.2_

  - [ ]* 12.3 Write property test: End-to-end pipeline detects removed trees
    - **Property 12: End-to-end pipeline detects removed trees from synthetic grid**
    - Generate regular grids, remove random subset, run `detect_missing_trees`, verify gaps near removed points
    - **Validates: Requirements 15.1, 15.2, 15.3**

  - [ ]* 12.4 Write unit tests for pipeline edge cases
    - Test `detect_missing_trees` with 0 points returns empty list
    - Test `detect_missing_trees` with 1 point returns empty list
    - Test `detect_missing_trees` with 2 points returns empty list
    - Test `detect_missing_trees` with a small known grid and known gaps
    - _Requirements: 15.5_

- [ ] 13. Update dependencies
  - [x] 13.1 Update `requirements.txt` with processing dependencies
    - Add `numpy>=1.24.0`, `pandas>=2.0.0`, `scipy>=1.10.0`, `scikit-learn>=1.2.0`, `alphashape>=1.3.0`, `shapely>=2.0.0`
    - _Requirements: 9, 10, 11, 12, 13, 14, 15_

- [ ] 14. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Implement REST API endpoint for missing trees
  - [x] 15.1 Create `src/server.py` with FastAPI app and `GET /orchards/{orchard_id}/missing-trees` endpoint
    - Create FastAPI app instance
    - Define `Coordinate` Pydantic response model with `lat` and `lng` fields
    - Implement `get_missing_trees(orchard_id: int)` endpoint handler
    - Read `AEROBOTICS_API_TOKEN` from environment, create `AeroboticsClient`
    - Call `fetch_orchard_data(client, orchard_id)` and extract `missing_trees`
    - Convert `(lat, lng)` tuples to list of `Coordinate` objects
    - Return empty list when no missing trees detected
    - _Requirements: 16.1, 16.2, 16.3_

  - [x] 15.2 Add error handling to the endpoint
    - Catch case where `fetch_orchard_data` returns empty survey (no surveys found) and raise `HTTPException(404)`
    - Catch `AeroboticsAPIError` from upstream API failures and raise `HTTPException(502)` with error detail
    - FastAPI handles invalid `orchard_id` type automatically (422 validation error)
    - _Requirements: 16.4, 16.5, 16.6_

  - [x] 15.3 Update `requirements.txt` with FastAPI dependencies
    - Add `fastapi>=0.100.0`, `uvicorn>=0.23.0`, `httpx>=0.24.0`
    - _Requirements: 16.1_

  - [ ]* 15.4 Write property test: API response shape matches coordinate contract
    - **Property 13: API response shape matches coordinate contract**
    - Generate random lists of (lat, lng) tuples (including empty), mock `fetch_orchard_data` to return them, use FastAPI TestClient, verify 200 response with correct JSON array shape
    - **Validates: Requirements 16.2, 16.3**

  - [ ]* 15.5 Write property test: Upstream API errors map to HTTP 502
    - **Property 14: Upstream API errors map to HTTP 502**
    - Generate random AeroboticsAPIError instances, mock `fetch_orchard_data` to raise them, verify 502 response with detail field
    - **Validates: Requirements 16.5**

  - [ ]* 15.6 Write unit tests for REST API endpoint
    - Test successful response returns 200 with `[{lat, lng}, ...]` shape
    - Test empty missing trees returns 200 with `[]`
    - Test no surveys returns 404 with error message
    - Test upstream API error returns 502 with error detail
    - Test non-integer orchardId returns 422
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5, 16.6_

- [ ] 16. Final checkpoint - Ensure all tests pass including API endpoint
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Property tests validate universal correctness properties using Hypothesis (with `hypothesis.extra.numpy` for array generation)
- Unit tests validate specific examples and edge cases using pytest + unittest.mock
- Tasks 9–12 cover the missing tree detection pipeline (Requirements 9–15)
- Tasks 15–16 cover the new REST API endpoint (Requirement 16) using FastAPI + TestClient
- The existing `src/procesing.py` script will be refactored into proper functions in `src/processing.py` (note: filename typo corrected)
