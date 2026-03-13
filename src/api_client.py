"""Aerobotics API client for fetching orchard survey data."""

from typing import Any

import requests


class AeroboticsAPIError(Exception):
    """Descriptive error for Aerobotics API failures."""

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        endpoint: str | None = None,
        response_body: str | None = None,
    ):
        self.status_code = status_code
        self.endpoint = endpoint
        self.response_body = response_body
        super().__init__(message)


class AeroboticsClient:
    """HTTP client for the Aerobotics farming API."""

    BASE_URL = "https://api.aerobotics.com"
    TIMEOUT = 30

    def __init__(self, api_token: str, base_url: str | None = None):
        """Initialize with Bearer token. Creates a persistent requests.Session."""
        self.base_url = base_url or self.BASE_URL
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {api_token}"})

    def _get(self, endpoint: str, params: dict | None = None) -> Any:
        """Send GET request to endpoint. Returns parsed JSON."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=self.TIMEOUT)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            body = exc.response.text if exc.response is not None else None
            raise AeroboticsAPIError(
                f"HTTP {status_code} error for {url}: {body}",
                status_code=status_code,
                endpoint=url,
                response_body=body,
            ) from exc
        except requests.RequestException as exc:
            raise AeroboticsAPIError(
                f"Request failed for {url}: {exc}",
                endpoint=url,
            ) from exc

    def _get_paginated(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Fetch all pages from a paginated endpoint."""
        all_results: list[dict] = []
        page = 1

        try:
            data = self._get(endpoint, params=params)
        except AeroboticsAPIError as exc:
            raise AeroboticsAPIError(
                f"Pagination failed on page {page} ({len(all_results)} records collected so far): {exc}",
                status_code=exc.status_code,
                endpoint=exc.endpoint,
                response_body=exc.response_body,
            ) from exc

        all_results.extend(data.get("results", []))
        next_url = data.get("next")

        while next_url is not None:
            page += 1
            try:
                response = self.session.get(next_url, timeout=self.TIMEOUT)
                response.raise_for_status()
                data = response.json()
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                body = exc.response.text if exc.response is not None else None
                raise AeroboticsAPIError(
                    f"Pagination failed on page {page} ({len(all_results)} records collected so far): HTTP {status_code} for {next_url}",
                    status_code=status_code,
                    endpoint=next_url,
                    response_body=body,
                ) from exc
            except requests.RequestException as exc:
                raise AeroboticsAPIError(
                    f"Pagination failed on page {page} ({len(all_results)} records collected so far): {exc}",
                    endpoint=next_url,
                ) from exc

            all_results.extend(data.get("results", []))
            next_url = data.get("next")

        return all_results

    def get_surveys(self, orchard_id: int) -> list[dict]:
        """Fetch all surveys for an orchard."""
        return self._get_paginated("/farming/surveys/", params={"orchard_id": orchard_id})

    def get_tree_summary(self, survey_id: int) -> dict:
        """Fetch tree survey summary. Raises if no summary available."""
        data = self._get(f"/farming/surveys/{survey_id}/tree_survey_summaries/")
        if not data:
            raise AeroboticsAPIError(
                f"No tree summary available for survey {survey_id}",
                endpoint=f"{self.base_url}/farming/surveys/{survey_id}/tree_survey_summaries/",
            )
        return data

    def get_tree_records(self, survey_id: int) -> list[dict]:
        """Fetch all individual tree records for a survey."""
        return self._get_paginated(f"/farming/surveys/{survey_id}/tree_surveys/")
