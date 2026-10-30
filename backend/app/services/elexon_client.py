"""Small standard-library client for the Elexon Insights API."""

from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
USER_AGENT = "wellfound-wind-dashboard/0.1"


class ElexonApiError(RuntimeError):
    """Raised when the Elexon API cannot return a valid response."""


def build_url(path: str, params: Mapping[str, str]) -> str:
    """Build an API URL from a fixed Elexon path and query parameters."""

    return f"{API_BASE}{path}?{urlencode(params)}"


def fetch_json(
    path: str,
    params: Mapping[str, str],
    *,
    timeout_seconds: int = 60,
) -> list[dict[str, Any]]:
    """Fetch and validate a JSON-array response from the Elexon API."""

    url = build_url(path, params)
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        },
    )

    try:
        with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - fixed official host
            payload = json.load(response)
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:500]
        raise ElexonApiError(
            f"Elexon returned HTTP {error.code} for {path}: {body}"
        ) from error
    except URLError as error:
        raise ElexonApiError(f"Could not reach Elexon for {path}: {error.reason}") from error
    except TimeoutError as error:
        raise ElexonApiError(f"Elexon request timed out for {path}") from error
    except json.JSONDecodeError as error:
        raise ElexonApiError(f"Elexon returned invalid JSON for {path}") from error

    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise ElexonApiError(f"Expected a JSON array of objects from {path}")

    return payload


def fetch_january_actuals() -> list[dict[str, Any]]:
    """Fetch January 2026 half-hourly wind actuals."""

    return fetch_json(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": "2026-01-01",
            "settlementDateTo": "2026-01-31",
            "fuelType": "WIND",
        },
    )


def fetch_forecast_buffer() -> list[dict[str, Any]]:
    """Fetch forecast revisions around the January 2026 delivery period."""

    return fetch_json(
        "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": "2025-12-01T00:00:00Z",
            "publishDateTimeTo": "2026-02-02T00:00:00Z",
        },
    )
