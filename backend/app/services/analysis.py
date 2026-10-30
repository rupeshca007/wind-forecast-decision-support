"""Pure analysis functions for forecast-versus-actual wind data."""

from __future__ import annotations

from collections import Counter, defaultdict
from math import floor, isfinite, sqrt
from statistics import fmean
from typing import Any, Mapping, Sequence


MATCHED = "matched"
KNOWN_STATUSES = {
    MATCHED,
    "missing_actual",
    "missing_forecast",
    "incomplete_actual",
    "invalid",
}


def _to_float(value: Any) -> float | None:
    """Convert a finite numeric value to float, returning None when absent/invalid."""

    if value is None or isinstance(value, bool):
        return None
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None
    return converted if isfinite(converted) else None


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    """Return a linearly interpolated percentile for a non-empty numeric sequence."""

    if not values:
        return None
    if not 0 <= percentile <= 100:
        raise ValueError("percentile must be between 0 and 100")

    ordered = sorted(values)
    rank = (len(ordered) - 1) * percentile / 100
    lower = floor(rank)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = rank - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def calculate_interval_errors(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Add numeric error fields to normalized rows without mutating the input."""

    enriched: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        actual = _to_float(row.get("actual_generation_mw"))
        forecast = _to_float(row.get("forecast_generation_mw"))
        status = row.get("match_status")

        if status is None and actual is not None and forecast is not None:
            status = MATCHED
        elif status not in KNOWN_STATUSES:
            status = "invalid"

        row["actual_generation_mw"] = actual
        row["forecast_generation_mw"] = forecast
        row["match_status"] = status

        if status == MATCHED and actual is not None and forecast is not None:
            signed_error = forecast - actual
            row["signed_error_mw"] = signed_error
            row["absolute_error_mw"] = abs(signed_error)
        else:
            if status == MATCHED:
                row["match_status"] = "invalid"
            row["signed_error_mw"] = None
            row["absolute_error_mw"] = None

        enriched.append(row)

    return enriched


def _error_rows(rows: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    return [
        row
        for row in rows
        if row.get("match_status") == MATCHED
        and row.get("signed_error_mw") is not None
        and row.get("absolute_error_mw") is not None
    ]


def _summarize_enriched(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate aggregate metrics from rows that already have error fields."""

    errors = _error_rows(rows)
    signed_errors = [float(row["signed_error_mw"]) for row in errors]
    absolute_errors = [float(row["absolute_error_mw"]) for row in errors]
    actuals = [float(row["actual_generation_mw"]) for row in errors]
    forecasts = [float(row["forecast_generation_mw"]) for row in errors]
    statuses = Counter(str(row.get("match_status", "invalid")) for row in rows)

    actual_total = sum(actuals)
    metrics: dict[str, Any] = {
        "interval_count": len(rows),
        "matched_intervals": len(errors),
        "unmatched_intervals": len(rows) - len(errors),
        "missing_actual_intervals": statuses.get("missing_actual", 0),
        "missing_forecast_intervals": statuses.get("missing_forecast", 0),
        "incomplete_actual_intervals": statuses.get("incomplete_actual", 0),
        "invalid_intervals": statuses.get("invalid", 0),
        "coverage": (len(errors) / len(rows)) if rows else None,
        "actual_mean_mw": fmean(actuals) if actuals else None,
        "forecast_mean_mw": fmean(forecasts) if forecasts else None,
        "mae_mw": fmean(absolute_errors) if absolute_errors else None,
        "rmse_mw": (
            sqrt(fmean([error * error for error in signed_errors]))
            if signed_errors
            else None
        ),
        "bias_mw": fmean(signed_errors) if signed_errors else None,
        "wape": (sum(absolute_errors) / actual_total) if actual_total else None,
        "p95_absolute_error_mw": _percentile(absolute_errors, 95),
        "max_absolute_error_mw": max(absolute_errors) if absolute_errors else None,
    }
    return metrics


def calculate_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Calculate aggregate accuracy and data-quality metrics."""

    return _summarize_enriched(calculate_interval_errors(rows))


def _delivery_date(row: Mapping[str, Any]) -> str:
    """Get the delivery date used for daily grouping."""

    value = row.get("delivery_date")
    if isinstance(value, str) and value:
        return value
    delivery_time = row.get("delivery_time")
    if isinstance(delivery_time, str) and len(delivery_time) >= 10:
        return delivery_time[:10]
    return "unknown"


def calculate_daily_metrics(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Return one accuracy summary per delivery date."""

    enriched = calculate_interval_errors(rows)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in enriched:
        grouped[_delivery_date(row)].append(row)

    daily: list[dict[str, Any]] = []
    for delivery_date in sorted(grouped):
        daily.append({"delivery_date": delivery_date, **_summarize_enriched(grouped[delivery_date])})
    return daily


def analyze_dataset(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Return enriched interval data, aggregate metrics, and daily metrics."""

    enriched = calculate_interval_errors(rows)
    return {
        "metrics": _summarize_enriched(enriched),
        "daily_metrics": calculate_daily_metrics(enriched),
        "series": enriched,
    }
