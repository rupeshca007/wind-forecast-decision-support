"""FastAPI entry point for the wind forecast dashboard."""

import os
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles

from .services.analysis import analyze_dataset
from .services.dataset_store import DatasetStore


JANUARY_START = date(2026, 1, 1)
JANUARY_END = date(2026, 1, 31)
dataset_store = DatasetStore()


class MetricFields(BaseModel):
    interval_count: int
    matched_intervals: int
    unmatched_intervals: int
    missing_actual_intervals: int
    missing_forecast_intervals: int
    incomplete_actual_intervals: int
    invalid_intervals: int
    coverage: float | None
    actual_mean_mw: float | None
    forecast_mean_mw: float | None
    mae_mw: float | None
    rmse_mw: float | None
    bias_mw: float | None
    wape: float | None
    p95_absolute_error_mw: float | None
    max_absolute_error_mw: float | None


class DailyMetricResponse(MetricFields):
    delivery_date: str


class SeriesPoint(BaseModel):
    delivery_time: str
    delivery_date: str
    decision_cutoff: str
    actual_generation_mw: float | None
    actual_half_hour_count: int
    forecast_generation_mw: float | None
    forecast_publish_time: str | None
    forecast_lead_hours: float | None
    match_status: str
    signed_error_mw: float | None
    absolute_error_mw: float | None


class AnalysisMetadata(BaseModel):
    source: str | None = None
    analysis_grain: str | None = None
    forecast_selection: str | None = None
    delivery_window_start: str | None = None
    delivery_window_end_exclusive: str | None = None
    expected_delivery_intervals: int | None = None
    query_start: str
    query_end: str


class AnalysisResponse(BaseModel):
    metadata: AnalysisMetadata
    metrics: MetricFields
    daily_metrics: list[DailyMetricResponse]
    series: list[SeriesPoint]


class DailyAnalysisResponse(BaseModel):
    metadata: AnalysisMetadata
    daily_metrics: list[DailyMetricResponse]


class HealthResponse(BaseModel):
    status: str
    data_loaded: bool
    data_rows: int


class DataStatusResponse(BaseModel):
    status: str
    data_loaded: bool
    row_count: int
    analysis_grain: str | None
    delivery_window_start: str | None
    delivery_window_end_exclusive: str | None
    matched_intervals: int | None
    data_error: str | None


app = FastAPI(
    title="January 2026 Wind Forecast API",
    version="0.1.0",
    description="Backend API for the Elexon wind forecast decision-support dashboard.",
)


def _cors_origins() -> list[str]:
    configured = os.getenv(
        "WIND_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )
    return [origin.strip() for origin in configured.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["GET"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["system"])
def health() -> HealthResponse:
    """Return a lightweight readiness response for local and deployed checks."""

    return HealthResponse(
        status="ok" if dataset_store.ready else "degraded",
        data_loaded=dataset_store.ready,
        data_rows=len(dataset_store.rows),
    )


def _validated_range(
    start: date | None,
    end: date | None,
) -> tuple[date, date]:
    selected_start = start or JANUARY_START
    selected_end = end or JANUARY_END

    if selected_start > selected_end:
        raise HTTPException(status_code=400, detail="start must be on or before end")
    if selected_start < JANUARY_START or selected_end > JANUARY_END:
        raise HTTPException(
            status_code=400,
            detail="date range must remain within January 2026",
        )
    return selected_start, selected_end


def _require_dataset() -> None:
    if not dataset_store.ready:
        raise HTTPException(
            status_code=503,
            detail=f"normalized dataset is unavailable: {dataset_store.error or 'unknown error'}",
        )


def _metadata(start: date, end: date) -> dict[str, Any]:
    return {
        **dataset_store.metadata,
        "query_start": start.isoformat(),
        "query_end": end.isoformat(),
    }


@app.get("/api/data-status", response_model=DataStatusResponse, tags=["system"])
def data_status() -> DataStatusResponse:
    """Return the loaded dataset's readiness and coverage information."""

    return DataStatusResponse(
        status="ready" if dataset_store.ready else "unavailable",
        data_loaded=dataset_store.ready,
        row_count=len(dataset_store.rows),
        analysis_grain=dataset_store.metadata.get("analysis_grain"),
        delivery_window_start=dataset_store.metadata.get("delivery_window_start"),
        delivery_window_end_exclusive=dataset_store.metadata.get("delivery_window_end_exclusive"),
        matched_intervals=dataset_store.metadata.get("status_counts", {}).get("matched"),
        data_error=dataset_store.error,
    )


@app.get("/api/analysis", response_model=AnalysisResponse, tags=["analysis"])
def analysis(
    start: date | None = Query(None, description="Inclusive delivery date, YYYY-MM-DD"),
    end: date | None = Query(None, description="Inclusive delivery date, YYYY-MM-DD"),
) -> AnalysisResponse:
    """Return interval series, aggregate metrics, and daily summaries."""

    _require_dataset()
    selected_start, selected_end = _validated_range(start, end)
    rows = dataset_store.filter_rows(selected_start, selected_end)
    result = analyze_dataset(rows)
    return AnalysisResponse(
        metadata=AnalysisMetadata(**_metadata(selected_start, selected_end)),
        **result,
    )


@app.get("/api/analysis/daily", response_model=DailyAnalysisResponse, tags=["analysis"])
def daily_analysis(
    start: date | None = Query(None, description="Inclusive delivery date, YYYY-MM-DD"),
    end: date | None = Query(None, description="Inclusive delivery date, YYYY-MM-DD"),
) -> DailyAnalysisResponse:
    """Return daily forecast-accuracy summaries for the selected range."""

    _require_dataset()
    selected_start, selected_end = _validated_range(start, end)
    result = analyze_dataset(dataset_store.filter_rows(selected_start, selected_end))
    return DailyAnalysisResponse(
        metadata=AnalysisMetadata(**_metadata(selected_start, selected_end)),
        daily_metrics=result["daily_metrics"],
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
configured_frontend_dist = os.getenv("FRONTEND_DIST_PATH")
frontend_dist = (
    Path(configured_frontend_dist)
    if configured_frontend_dist
    else PROJECT_ROOT / "frontend" / "dist"
)

if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
