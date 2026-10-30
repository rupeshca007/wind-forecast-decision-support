"""Normalize Elexon records into hourly January 2026 analysis rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any


UTC = timezone.utc
JANUARY_START = datetime(2026, 1, 1, tzinfo=UTC)
FEBRUARY_START = datetime(2026, 2, 1, tzinfo=UTC)


def parse_timestamp(value: Any, field_name: str) -> datetime:
    """Parse an ISO-8601 timestamp and return it in UTC."""

    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{field_name} is not a valid ISO-8601 timestamp: {value}") from error

    if parsed.tzinfo is None:
        raise ValueError(f"{field_name} must include timezone information")
    return parsed.astimezone(UTC)


def format_timestamp(value: datetime | None) -> str | None:
    """Format a UTC timestamp consistently for CSV and JSON output."""

    if value is None:
        return None
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_generation(value: Any, field_name: str) -> float:
    """Convert a generation field to a finite MW number."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be numeric")
    return float(value)


def _is_january(value: datetime) -> bool:
    return JANUARY_START <= value < FEBRUARY_START


def _delivery_hour(value: datetime) -> datetime:
    return value.replace(minute=0, second=0, microsecond=0)


def decision_cutoff(delivery_day: date) -> datetime:
    """Return the default previous-day decision cutoff in UTC."""

    previous_day = delivery_day - timedelta(days=1)
    return datetime.combine(previous_day, time(23, 59, 59), tzinfo=UTC)


def _choose_latest_revision(
    current: dict[str, Any] | None,
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Choose the later published record, with stable tie behavior."""

    if current is None:
        return candidate
    if candidate["publish_time"] >= current["publish_time"]:
        return candidate
    return current


def normalize_actuals(
    rows: list[dict[str, Any]],
) -> tuple[dict[datetime, dict[str, Any]], dict[str, int]]:
    """Deduplicate half-hour actuals and aggregate them to hourly MW."""

    latest_by_half_hour: dict[datetime, dict[str, Any]] = {}
    stats = {
        "raw_records": len(rows),
        "invalid_records": 0,
        "non_wind_records": 0,
        "duplicate_half_hour_records": 0,
    }

    for row in rows:
        try:
            if row.get("fuelType") != "WIND":
                stats["non_wind_records"] += 1
                continue
            start_time = parse_timestamp(row.get("startTime"), "startTime")
            publish_time = parse_timestamp(row.get("publishTime"), "publishTime")
            generation = parse_generation(row.get("generation"), "generation")
            if not _is_january(start_time) or start_time.minute not in {0, 30}:
                stats["invalid_records"] += 1
                continue
        except ValueError:
            stats["invalid_records"] += 1
            continue

        candidate = {
            "start_time": start_time,
            "publish_time": publish_time,
            "generation_mw": generation,
        }
        if start_time in latest_by_half_hour:
            stats["duplicate_half_hour_records"] += 1
        latest_by_half_hour[start_time] = _choose_latest_revision(
            latest_by_half_hour.get(start_time), candidate
        )

    grouped: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in latest_by_half_hour.values():
        grouped[_delivery_hour(row["start_time"])].append(row)

    hourly: dict[datetime, dict[str, Any]] = {}
    for hour, half_hours in grouped.items():
        generations = [row["generation_mw"] for row in half_hours]
        hourly[hour] = {
            "actual_generation_mw": sum(generations) / len(generations),
            "actual_half_hour_count": len(half_hours),
        }

    stats["valid_half_hour_records"] = len(latest_by_half_hour)
    stats["hourly_actual_intervals"] = len(hourly)
    stats["incomplete_hourly_actuals"] = sum(
        value["actual_half_hour_count"] != 2 for value in hourly.values()
    )
    return hourly, stats


def select_latest_forecasts(
    rows: list[dict[str, Any]],
) -> tuple[dict[datetime, dict[str, Any]], dict[str, int]]:
    """Select the latest forecast available at the default decision cutoff."""

    revisions: dict[tuple[datetime, datetime], dict[str, Any]] = {}
    stats = {
        "raw_records": len(rows),
        "invalid_records": 0,
        "duplicate_target_revision_records": 0,
        "january_target_records": 0,
        "january_target_intervals": 0,
        "no_eligible_forecast_intervals": 0,
    }

    for row in rows:
        try:
            start_time = parse_timestamp(row.get("startTime"), "startTime")
            publish_time = parse_timestamp(row.get("publishTime"), "publishTime")
            generation = parse_generation(row.get("generation"), "generation")
            if not _is_january(start_time) or start_time.minute != 0:
                continue
        except ValueError:
            stats["invalid_records"] += 1
            continue

        stats["january_target_records"] += 1
        key = (start_time, publish_time)
        candidate = {
            "start_time": start_time,
            "publish_time": publish_time,
            "generation_mw": generation,
        }
        if key in revisions:
            stats["duplicate_target_revision_records"] += 1
        revisions[key] = candidate

    target_times = sorted({key[0] for key in revisions})
    stats["january_target_intervals"] = len(target_times)
    selected: dict[datetime, dict[str, Any]] = {}

    for target_time in target_times:
        cutoff = decision_cutoff(target_time.date())
        eligible = [
            row
            for (start_time, _), row in revisions.items()
            if start_time == target_time and row["publish_time"] <= cutoff
        ]
        if not eligible:
            stats["no_eligible_forecast_intervals"] += 1
            continue
        selected[target_time] = max(eligible, key=lambda row: row["publish_time"])

    stats["selected_forecast_intervals"] = len(selected)
    return selected, stats


def normalize_january_dataset(
    actual_rows: list[dict[str, Any]],
    forecast_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create one hourly row for every January 2026 delivery hour."""

    actuals, actual_stats = normalize_actuals(actual_rows)
    forecasts, forecast_stats = select_latest_forecasts(forecast_rows)

    output: list[dict[str, Any]] = []
    current = JANUARY_START
    while current < FEBRUARY_START:
        cutoff = decision_cutoff(current.date())
        actual = actuals.get(current)
        forecast = forecasts.get(current)
        has_actual = actual is not None
        has_forecast = forecast is not None

        if not has_actual:
            match_status = "missing_actual"
        elif actual["actual_half_hour_count"] != 2:
            match_status = "incomplete_actual"
        elif not has_forecast:
            match_status = "missing_forecast"
        else:
            match_status = "matched"

        lead_hours = None
        if forecast is not None:
            lead_hours = round(
                (current - forecast["publish_time"]).total_seconds() / 3600,
                3,
            )

        output.append(
            {
                "delivery_time": format_timestamp(current),
                "delivery_date": current.date().isoformat(),
                "decision_cutoff": format_timestamp(cutoff),
                "actual_generation_mw": (
                    round(actual["actual_generation_mw"], 6) if actual else None
                ),
                "actual_half_hour_count": actual["actual_half_hour_count"] if actual else 0,
                "forecast_generation_mw": (
                    round(forecast["generation_mw"], 6) if forecast else None
                ),
                "forecast_publish_time": (
                    format_timestamp(forecast["publish_time"]) if forecast else None
                ),
                "forecast_lead_hours": lead_hours,
                "match_status": match_status,
            }
        )
        current += timedelta(hours=1)

    status_counts: dict[str, int] = defaultdict(int)
    for row in output:
        status_counts[row["match_status"]] += 1

    metadata: dict[str, Any] = {
        "delivery_window_start": format_timestamp(JANUARY_START),
        "delivery_window_end_exclusive": format_timestamp(FEBRUARY_START),
        "analysis_grain": "hourly",
        "forecast_selection": "latest publishTime <= previous day 23:59:59 UTC",
        "expected_delivery_intervals": len(output),
        "status_counts": dict(sorted(status_counts.items())),
        "actuals": actual_stats,
        "forecasts": forecast_stats,
    }
    return output, metadata
