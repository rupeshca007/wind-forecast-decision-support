from math import isclose, sqrt

from backend.app.services.analysis import (
    analyze_dataset,
    calculate_daily_metrics,
    calculate_interval_errors,
    calculate_metrics,
)


def test_accuracy_metrics_are_calculated_from_matched_rows() -> None:
    rows = [
        {
            "delivery_time": "2026-01-01T00:00:00Z",
            "delivery_date": "2026-01-01",
            "actual_generation_mw": 100,
            "forecast_generation_mw": 110,
            "match_status": "matched",
        },
        {
            "delivery_time": "2026-01-01T01:00:00Z",
            "delivery_date": "2026-01-01",
            "actual_generation_mw": 200,
            "forecast_generation_mw": 180,
            "match_status": "matched",
        },
    ]

    metrics = calculate_metrics(rows)

    assert metrics["matched_intervals"] == 2
    assert isclose(metrics["mae_mw"], 15.0)
    assert isclose(metrics["rmse_mw"], sqrt(250))
    assert isclose(metrics["bias_mw"], -5.0)
    assert isclose(metrics["wape"], 0.1)
    assert isclose(metrics["p95_absolute_error_mw"], 19.5)
    assert isclose(metrics["max_absolute_error_mw"], 20.0)


def test_missing_rows_are_excluded_from_accuracy_but_counted() -> None:
    rows = [
        {
            "delivery_time": "2026-01-01T00:00:00Z",
            "delivery_date": "2026-01-01",
            "actual_generation_mw": 100,
            "forecast_generation_mw": 90,
            "match_status": "matched",
        },
        {
            "delivery_time": "2026-01-01T01:00:00Z",
            "delivery_date": "2026-01-01",
            "actual_generation_mw": 100,
            "forecast_generation_mw": None,
            "match_status": "missing_forecast",
        },
    ]

    enriched = calculate_interval_errors(rows)
    metrics = calculate_metrics(enriched)

    assert enriched[0]["signed_error_mw"] == -10.0
    assert enriched[1]["absolute_error_mw"] is None
    assert metrics["interval_count"] == 2
    assert metrics["matched_intervals"] == 1
    assert metrics["missing_forecast_intervals"] == 1
    assert metrics["coverage"] == 0.5


def test_daily_metrics_and_full_analysis_are_available() -> None:
    rows = [
        {
            "delivery_time": "2026-01-01T00:00:00Z",
            "delivery_date": "2026-01-01",
            "actual_generation_mw": 100,
            "forecast_generation_mw": 110,
            "match_status": "matched",
        },
        {
            "delivery_time": "2026-01-02T00:00:00Z",
            "delivery_date": "2026-01-02",
            "actual_generation_mw": 200,
            "forecast_generation_mw": 180,
            "match_status": "matched",
        },
    ]

    daily = calculate_daily_metrics(rows)
    result = analyze_dataset(rows)

    assert [item["delivery_date"] for item in daily] == ["2026-01-01", "2026-01-02"]
    assert result["metrics"]["matched_intervals"] == 2
    assert len(result["daily_metrics"]) == 2
    assert result["series"][0]["absolute_error_mw"] == 10.0
