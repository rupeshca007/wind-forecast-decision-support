"""Validate the Elexon API contract and save small raw response samples.

This script intentionally uses only Python's standard library so it can be run
before the backend dependencies are installed.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen


API_BASE = "https://data.elexon.co.uk/bmrs/api/v1"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"

JANUARY_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
FEBRUARY_START = datetime(2026, 2, 1, tzinfo=timezone.utc)


def fetch_json(path: str, params: dict[str, str]) -> list[dict[str, Any]]:
    """Fetch a JSON array from the Elexon Insights API."""

    url = f"{API_BASE}{path}?{urlencode(params)}"
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "wellfound-wind-dashboard/0.1",
        },
    )

    with urlopen(request, timeout=60) as response:  # noqa: S310 - fixed official API host
        payload = json.load(response)

    if not isinstance(payload, list):
        raise ValueError(f"Expected a JSON array from {path}, got {type(payload).__name__}")

    if any(not isinstance(row, dict) for row in payload):
        raise ValueError(f"Expected object records from {path}")

    return payload


def parse_timestamp(value: Any, field: str) -> datetime:
    """Parse an ISO-8601 timestamp and require timezone information."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO-8601 string")

    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{field} must include timezone information")
    return parsed.astimezone(timezone.utc)


def validate_actuals(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"dataset", "publishTime", "startTime", "fuelType", "generation"}
    january_rows: list[dict[str, Any]] = []

    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"FUELHH record is missing fields: {sorted(missing)}")
        if row["fuelType"] != "WIND":
            raise ValueError(f"FUELHH response contained non-WIND fuel type: {row['fuelType']}")
        parse_timestamp(row["publishTime"], "publishTime")
        start_time = parse_timestamp(row["startTime"], "startTime")
        if not isinstance(row["generation"], (int, float)):
            raise ValueError("FUELHH generation must be numeric")
        if JANUARY_START <= start_time < FEBRUARY_START:
            january_rows.append(row)

    return january_rows


def validate_forecasts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    required = {"dataset", "publishTime", "startTime", "generation"}
    january_rows: list[dict[str, Any]] = []

    for row in rows:
        missing = required - row.keys()
        if missing:
            raise ValueError(f"WINDFOR record is missing fields: {sorted(missing)}")
        publish_time = parse_timestamp(row["publishTime"], "publishTime")
        start_time = parse_timestamp(row["startTime"], "startTime")
        if not isinstance(row["generation"], (int, float)):
            raise ValueError("WINDFOR generation must be numeric")
        if JANUARY_START <= start_time < FEBRUARY_START:
            january_rows.append(row)
        if publish_time.tzinfo is None:
            raise ValueError("WINDFOR publishTime must include timezone information")

    return january_rows


def write_sample(filename: str, rows: list[dict[str, Any]], sample_size: int = 10) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / filename
    with path.open("w", encoding="utf-8") as output:
        json.dump(rows[:sample_size], output, indent=2)
        output.write("\n")


def observed_grain(rows: list[dict[str, Any]]) -> str:
    minutes = {
        parse_timestamp(row["startTime"], "startTime").minute for row in rows
    }
    if minutes == {0}:
        return "hourly"
    if minutes == {0, 30}:
        return "half-hourly"
    return f"mixed ({sorted(minutes)} minute values)"


def main() -> None:
    actuals = fetch_json(
        "/datasets/FUELHH/stream",
        {
            "settlementDateFrom": "2026-01-01",
            "settlementDateTo": "2026-01-31",
            "fuelType": "WIND",
        },
    )
    forecasts = fetch_json(
        "/datasets/WINDFOR/stream",
        {
            "publishDateTimeFrom": "2025-12-01T00:00:00Z",
            "publishDateTimeTo": "2026-02-02T00:00:00Z",
        },
    )

    january_actuals = validate_actuals(actuals)
    january_forecasts = validate_forecasts(forecasts)
    forecast_intervals = {row["startTime"] for row in january_forecasts}

    if not january_actuals:
        raise ValueError("No January 2026 FUELHH actuals were returned")
    if not january_forecasts:
        raise ValueError("No January 2026 WINDFOR target intervals were returned")

    write_sample("fuelhh_sample.json", january_actuals)
    write_sample("windfor_sample.json", january_forecasts)

    print("Elexon API validation passed")
    print(f"FUELHH raw records: {len(actuals)}")
    print(f"FUELHH January records: {len(january_actuals)}")
    print(f"FUELHH observed grain: {observed_grain(january_actuals)}")
    print(f"WINDFOR raw records: {len(forecasts)}")
    print(f"WINDFOR January target records: {len(january_forecasts)}")
    print(f"WINDFOR unique January target intervals: {len(forecast_intervals)}")
    print(f"WINDFOR observed grain: {observed_grain(january_forecasts)}")
    print(f"Samples written to: {RAW_DIR}")


if __name__ == "__main__":
    main()
