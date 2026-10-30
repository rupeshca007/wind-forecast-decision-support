from datetime import datetime, timezone

from backend.app.services.data_normalizer import normalize_january_dataset


UTC = timezone.utc


def test_normalizer_aggregates_actuals_and_uses_latest_eligible_forecast() -> None:
    actuals = [
        {
            "dataset": "FUELHH",
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T00:30:00Z",
            "generation": 100,
        },
        {
            "dataset": "FUELHH",
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:30:00Z",
            "publishTime": "2026-01-01T01:00:00Z",
            "generation": 200,
        },
    ]
    forecasts = [
        {
            "dataset": "WINDFOR",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2025-12-31T10:00:00Z",
            "generation": 150,
        },
        {
            "dataset": "WINDFOR",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T00:01:00Z",
            "generation": 999,
        },
    ]

    rows, metadata = normalize_january_dataset(actuals, forecasts)
    first = rows[0]

    assert first["actual_generation_mw"] == 150.0
    assert first["forecast_generation_mw"] == 150.0
    assert first["forecast_publish_time"] == "2025-12-31T10:00:00Z"
    assert first["match_status"] == "matched"
    assert metadata["status_counts"]["matched"] == 1
    assert metadata["status_counts"]["missing_actual"] == 743


def test_normalizer_marks_incomplete_actuals() -> None:
    actuals = [
        {
            "dataset": "FUELHH",
            "fuelType": "WIND",
            "startTime": "2026-01-01T00:00:00Z",
            "publishTime": "2026-01-01T00:30:00Z",
            "generation": 100,
        }
    ]

    rows, _ = normalize_january_dataset(actuals, [])

    assert rows[0]["actual_half_hour_count"] == 1
    assert rows[0]["match_status"] == "incomplete_actual"
