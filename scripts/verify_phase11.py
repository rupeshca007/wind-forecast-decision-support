#!/usr/bin/env python3
"""Run smoke checks against a deployed Wind Forecast Decision Support app."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def _get(base_url: str, path: str) -> tuple[int, str]:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    request = Request(url, headers={"User-Agent": "wind-forecast-phase11-smoke-test/1.0"})
    try:
        with urlopen(request, timeout=30) as response:
            return response.status, response.read().decode("utf-8")
    except HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {error.code} from {url}: {body[:240]}") from error
    except URLError as error:
        raise RuntimeError(f"could not reach {url}: {error.reason}") from error


def _json(base_url: str, path: str) -> dict:
    status, body = _get(base_url, path)
    if status != 200:
        raise RuntimeError(f"expected HTTP 200 for {path}, received {status}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{path} did not return valid JSON") from error
    if not isinstance(payload, dict):
        raise RuntimeError(f"{path} returned a JSON value instead of an object")
    return payload


def _check(name: str, assertion: Callable[[], None]) -> None:
    try:
        assertion()
    except Exception as error:  # noqa: BLE001 - convert every failed check to a clear report
        print(f"FAIL {name}: {error}")
        raise
    print(f"PASS {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base-url",
        default=os.getenv("DEPLOYMENT_URL"),
        help="deployed app URL, or set DEPLOYMENT_URL",
    )
    args = parser.parse_args()
    if not args.base_url:
        parser.error("--base-url is required unless DEPLOYMENT_URL is set")

    base_url = args.base_url.rstrip("/")
    query = urlencode({"start": "2026-01-01", "end": "2026-01-31"})

    _check(
        "dashboard",
        lambda: _assert_dashboard(base_url),
    )

    health = _json(base_url, "/api/health")
    _check(
        "health readiness",
        lambda: _assert_health(health),
    )

    status = _json(base_url, "/api/data-status")
    _check(
        "dataset status",
        lambda: _assert_data_status(status),
    )

    analysis = _json(base_url, f"/api/analysis?{query}")
    _check(
        "full January analysis",
        lambda: _assert_analysis(analysis),
    )

    print("Phase 11 deployment verification complete")
    return 0


def _assert_dashboard(base_url: str) -> None:
    status, body = _get(base_url, "/")
    if status != 200:
        raise RuntimeError(f"expected HTTP 200, received {status}")
    if "Wind Forecast Decision Support" not in body:
        raise RuntimeError("dashboard title was not found")


def _assert_health(payload: dict) -> None:
    if payload.get("status") != "ok":
        raise RuntimeError(f"unexpected status: {payload.get('status')!r}")
    if payload.get("data_loaded") is not True:
        raise RuntimeError("normalized dataset is not loaded")
    if payload.get("data_rows") != 744:
        raise RuntimeError(f"expected 744 data rows, received {payload.get('data_rows')!r}")


def _assert_data_status(payload: dict) -> None:
    if payload.get("status") != "ready":
        raise RuntimeError(f"unexpected dataset status: {payload.get('status')!r}")
    if payload.get("row_count") != 744:
        raise RuntimeError(f"expected 744 rows, received {payload.get('row_count')!r}")
    if payload.get("data_error") is not None:
        raise RuntimeError(f"dataset error: {payload.get('data_error')}")


def _assert_analysis(payload: dict) -> None:
    metrics = payload.get("metrics")
    daily_metrics = payload.get("daily_metrics")
    series = payload.get("series")
    if not isinstance(metrics, dict):
        raise RuntimeError("metrics object is missing")
    if metrics.get("interval_count") != 744:
        raise RuntimeError(f"expected 744 intervals, received {metrics.get('interval_count')!r}")
    if metrics.get("matched_intervals") != 744:
        raise RuntimeError(f"expected 744 matched intervals, received {metrics.get('matched_intervals')!r}")
    if not isinstance(daily_metrics, list) or len(daily_metrics) != 31:
        raise RuntimeError("expected 31 daily metric rows")
    if not isinstance(series, list) or len(series) != 744:
        raise RuntimeError("expected 744 interval series rows")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:
        raise SystemExit(1)
