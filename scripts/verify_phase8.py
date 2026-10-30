"""Run deterministic production-readiness checks against the local dataset and API models."""

from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.main import analysis, data_status, health  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
    print(f"PASS  {message}")


def main() -> None:
    status = health()
    dataset = data_status()
    response = analysis(None, None)

    check(status.status == "ok", "health endpoint reports ready")
    check(status.data_rows == 744, "normalized dataset contains 744 hourly rows")
    check(dataset.row_count == 744, "data-status reports 744 rows")
    check(dataset.matched_intervals == 744, "all hourly intervals are matched")
    check(response.metrics.interval_count == 744, "analysis covers 744 intervals")
    check(response.metrics.coverage == 1.0, "analysis coverage is 100 percent")
    check(len(response.daily_metrics) == 31, "analysis contains 31 daily summaries")
    check(len(response.series) == 744, "analysis contains 744 chart points")
    check(all(point.match_status == "matched" for point in response.series), "every chart point is matched")

    timestamps = [
        datetime.fromisoformat(point.delivery_time.replace("Z", "+00:00"))
        for point in response.series
    ]
    check(min(timestamps) == datetime(2026, 1, 1, tzinfo=timezone.utc), "series starts at January 1 UTC")
    check(max(timestamps) == datetime(2026, 1, 31, 23, tzinfo=timezone.utc), "series ends at January 31 23:00 UTC")
    check(math.isfinite(response.metrics.mae_mw or math.nan), "MAE is a finite number")
    check(math.isfinite(response.metrics.rmse_mw or math.nan), "RMSE is a finite number")
    response.model_dump_json()
    print("PASS  analysis response serializes as JSON")
    print("Phase 8 verification complete")


if __name__ == "__main__":
    main()
