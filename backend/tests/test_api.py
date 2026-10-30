from datetime import date

import pytest
from fastapi import HTTPException

from backend.app.main import analysis, app, daily_analysis, data_status, health


def test_health_reports_loaded_dataset() -> None:
    response = health()

    assert response.status == "ok"
    assert response.data_loaded is True
    assert response.data_rows == 744


def test_analysis_returns_full_january_result() -> None:
    response = analysis(None, None)

    assert response.metrics.interval_count == 744
    assert response.metrics.matched_intervals == 744
    assert len(response.series) == 744
    assert len(response.daily_metrics) == 31


def test_analysis_supports_inclusive_date_filters() -> None:
    response = analysis(date(2026, 1, 1), date(2026, 1, 2))

    assert response.metrics.interval_count == 48
    assert response.metadata.query_start == "2026-01-01"
    assert response.metadata.query_end == "2026-01-02"


def test_analysis_rejects_dates_outside_assignment_scope() -> None:
    with pytest.raises(HTTPException) as error:
        analysis(date(2025, 12, 31), date(2026, 1, 1))

    assert error.value.status_code == 400


def test_analysis_rejects_reversed_date_ranges() -> None:
    with pytest.raises(HTTPException) as error:
        analysis(date(2026, 1, 10), date(2026, 1, 1))

    assert error.value.status_code == 400


def test_analysis_response_is_json_serializable() -> None:
    response = analysis(date(2026, 1, 1), date(2026, 1, 1))

    payload = response.model_dump()

    assert payload["metrics"]["interval_count"] == 24
    assert payload["metadata"]["query_start"] == "2026-01-01"


def test_daily_endpoint_and_data_status_are_available() -> None:
    daily = daily_analysis(None, None)
    status = data_status()

    assert len(daily.daily_metrics) == 31
    assert status.status == "ready"
    assert status.row_count == 744


def test_expected_routes_are_registered() -> None:
    paths = {route.path for route in app.routes}

    assert {"/api/health", "/api/data-status", "/api/analysis", "/api/analysis/daily"} <= paths
