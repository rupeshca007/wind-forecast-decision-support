# January 2026 Wind Forecast Decision Support

## Project status

Phase 10 is complete: the project now has a single-image production deployment path for Render or any Docker host, in addition to the local Docker Compose setup. Phases 1–9 defined the product scope, repository foundation, API contract, normalized data pipeline, analysis service, backend endpoints, frontend dashboard, production-readiness checks, and delivery packaging.

## Repository structure

```text
frontend/                 React + Vite application
backend/                  FastAPI application
  app/main.py             API entry point and analysis endpoints
data/raw/                 Local raw API responses, not committed
data/processed/           Normalized dataset artifact used by the API and CI
scripts/                  Data-fetching and maintenance scripts
tests/                    Cross-project test fixtures and tests
```

## Phase 2 local setup

Backend:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

The backend health check is available at `http://localhost:8000/api/health`. The frontend remains a presentation shell while the backend API and data pipeline are completed in later phases.

## Product objective

This application will help a UK energy utility review national wind-generation forecasts available before day-ahead buying decisions and quantify how accurate those forecasts were during January 2026.

The application is an analysis and decision-support dashboard. It is not a trading system, a demand forecast, or a new machine-learning forecasting model.

## In-scope data

The application will use only the two Elexon datasets specified in the assignment:

- Actual generation: [FUELHH stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
  - Filter: `fuelType = WIND`
  - Delivery key: `startTime`
  - Value: `generation` in MW
  - Source resolution: 30 minutes
- Forecast generation: [WINDFOR stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
  - Delivery key: `startTime`
  - Forecast revision key: `publishTime`
  - Value: `generation` in MW

No demand, electricity-price, weather, plant-capacity, or procurement data will be added in the first version.

## Time and date rules

- All internal timestamps will be parsed and stored as timezone-aware UTC timestamps.
- The delivery window is the half-open interval `[2026-01-01T00:00:00Z, 2026-02-01T00:00:00Z)`.
- The application will display the January 2026 delivery date in the user interface, while retaining the UTC timestamp used for calculations.
- The initial forecast-ingestion buffer will cover forecast publications from December 2025 through February 1, 2026. The query parameters are validated against Elexon's OpenAPI definition by `scripts/validate_elexon_api.py`.

### Phase 3 API validation finding

The official OpenAPI definition was checked and the January 2026 endpoints were queried successfully. `FUELHH` returned 30-minute records, while the observed `WINDFOR` January target records had hourly `startTime` values. The analysis grain will therefore be hourly:

```text
hourly_actual_mw = mean(two consecutive FUELHH 30-minute generation values)
```

The forecast will be joined to the hourly actual using the normalized hourly `startTime`. This preserves the source data and avoids duplicating an hourly forecast across two half-hour intervals.

The validation run returned 1,488 January actual half-hour records, 18,104 January forecast revisions covering 744 unique hourly target intervals, and saved small response samples under `data/raw/`.

Run the validation again with:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/validate_elexon_api.py
```

## Phase 4 data pipeline

The normalization pipeline is split into three responsibilities:

- `backend/app/services/elexon_client.py` owns the two Elexon API requests and response validation.
- `backend/app/services/data_normalizer.py` parses timestamps, deduplicates revisions, aggregates actuals to hourly MW, applies the forecast cutoff, and joins the series.
- `scripts/fetch_january_2026.py` persists full raw responses locally and writes the normalized analysis files.

Run it with:

```bash
PYTHONDONTWRITEBYTECODE=1 python scripts/fetch_january_2026.py
```

The latest run produced 744 hourly rows, all with `match_status = matched`:

```text
data/processed/january_2026.csv
data/processed/january_2026_metadata.json
```

Full raw responses are ignored by Git. The normalized CSV and metadata remain available for deterministic local and CI runs; small raw samples remain available in `data/raw/` for tests and contract review.

## Phase 5 analysis service

`backend/app/services/analysis.py` provides pure functions for:

- signed and absolute interval errors
- MAE, RMSE, bias, WAPE, and 95th-percentile absolute error
- coverage and missing/incomplete/invalid interval counts
- daily accuracy summaries
- a combined response containing metrics, daily metrics, and the enriched time series

The January 2026 normalized dataset currently produces 744 matched hourly intervals, with 100% coverage. Accuracy metrics are calculated only from matched intervals; data-quality counts remain visible separately.

## Phase 6 analysis API

`backend/app/main.py` exposes the normalized January dataset through FastAPI. `backend/app/services/dataset_store.py` loads the processed CSV once at startup, validates the required columns, and applies inclusive date filters without mutating the source data.

Available endpoints:

- `GET /api/health` reports service status and whether the dataset is loaded.
- `GET /api/data-status` reports the processed row count, date range, and metadata status.
- `GET /api/analysis` returns aggregate metrics, daily summaries, chart-ready interval series, and metadata.
- `GET /api/analysis/daily` returns only daily accuracy summaries.

The analysis endpoints accept optional inclusive query parameters:

```text
/api/analysis?start=2026-01-01&end=2026-01-07
```

Dates outside January 2026 are rejected. The API uses the Phase 4 forecast-selection rule and reports that rule in the response metadata; it does not silently change the cutoff per request.

Run the backend locally with:

```bash
source .venv/bin/activate
uvicorn backend.app.main:app --reload --port 8000
```

API contract tests are in `backend/tests/test_api.py` and cover dataset loading, date filtering, validation errors, response shape, and route registration.

## Phase 7 dashboard frontend

`frontend/src/App.tsx` now connects the frontend to `VITE_API_BASE_URL` and renders the Phase 6 `/api/analysis` response. The dashboard includes:

- inclusive January 2026 date-range controls with a full-month shortcut
- coverage, MAE, RMSE, and bias KPI cards
- forecast-versus-actual hourly line chart
- signed forecast-error interval chart
- weighted error, p95 miss, and maximum miss readout
- daily accuracy table with actual, forecast, MAE, bias, and coverage
- loading, retry, API error, and responsive mobile states

Install and build the frontend with:

```bash
cd frontend
npm install
npm run build
```

Start the development UI with `npm run dev`. Set `VITE_API_BASE_URL` when the backend is not running at `http://localhost:8000`.

To run both services without Docker, from the repository root use:

```bash
./scripts/run_local.sh
```

Open `http://localhost:5173` in the browser. `http://localhost` uses port 80 and will show a connection-refused error unless the Docker/Nginx deployment is running.

## Phase 8 integration and verification

The local development setup now proxies `/api` from Vite to the FastAPI server. With the default configuration, the browser uses the same-origin path and Vite forwards requests to `http://localhost:8000`, avoiding manual CORS configuration during development. Copy `frontend/.env.example` to `frontend/.env` if the proxy target needs changing. For a separate deployed backend, set `VITE_API_BASE_URL` to its base URL.

FastAPI accepts these environment settings:

- `WIND_CORS_ORIGINS`: comma-separated allowed browser origins; defaults to both localhost Vite variants.
- `WIND_DATA_PATH`: optional path to a normalized CSV; defaults to `data/processed/january_2026.csv`.

Run the deterministic Phase 8 verification after refreshing the processed dataset:

```bash
source .venv/bin/activate
python scripts/verify_phase8.py
```

The verification checks dataset readiness, 744 hourly intervals, complete matching, January UTC boundaries, finite accuracy metrics, daily summaries, chart-point count, and response serialization. Backend tests remain in `backend/tests/test_api.py`; the frontend is validated with `npm run typecheck` and `npm run build`.

## Phase 9 delivery packaging

The repository includes a two-service Docker Compose deployment:

- `backend/Dockerfile` runs FastAPI on port 8000 and fetches the normalized January dataset at startup if it is not already available.
- `frontend/Dockerfile` builds the React dashboard and serves it with Nginx on port 80.
- `frontend/nginx.conf` proxies `/api` requests to the backend service and supports the client-side application route.
- `.github/workflows/ci.yml` runs backend tests, Phase 8 verification, frontend typechecking, and the production build on pushes and pull requests.

Start the complete deployment with Docker:

```bash
docker compose up --build
```

Then open `http://localhost`. The API remains available at `http://localhost:8000/api/health`. The first backend start may take longer because it downloads the official Elexon source data when the ignored processed CSV is absent.

Full raw API responses remain excluded from Git by design. The normalized CSV and metadata are small enough to keep as reproducible application artifacts, while `scripts/fetch_january_2026.py` can refresh them from the official source.

## Phase 10 deployment

Phase 10 packages the dashboard and API into one production image. The root `Dockerfile` builds the React app, copies it into the Python image, and serves both surfaces from FastAPI:

- `/` serves the React dashboard.
- `/api/health` and `/api/*` serve the backend.
- `PORT` is respected for cloud platforms; local Docker defaults to port 8000.
- If the normalized CSV is missing, the container refreshes it from the official Elexon API before starting.

### Recommended deployment: Render

The repository includes `render.yaml`, so deployment can be done without creating separate frontend and backend services:

1. Push this repository to GitHub.
2. In Render, choose **New → Blueprint** and connect the repository.
3. Render reads `render.yaml`, builds the root `Dockerfile`, and uses `/api/health` as the health check.
4. Wait for the deploy to finish, then open the generated `onrender.com` URL.

Render requires web services to bind to `0.0.0.0` and the environment-provided `PORT`; the production Dockerfile already does this. See the [Render web service documentation](https://render.com/docs/web-services) and [Blueprint reference](https://render.com/docs/blueprint-spec).

### Deploy on any Docker host

```bash
docker build -t wellfound-wind-dashboard .
docker run --rm -p 8000:8000 wellfound-wind-dashboard
```

Open `http://localhost:8000`. For a cloud provider, map its assigned port to the container and keep the process command unchanged so `${PORT}` is honored.

## Phase 11 release verification

Phase 11 adds a repeatable smoke test for the deployed application. It checks the public dashboard, API readiness, normalized dataset status, and the complete January 2026 analysis response without requiring any credentials.

Run it against the Render deployment with:

```bash
python scripts/verify_phase11.py \
  --base-url https://wellfound-wind-dashboard.onrender.com
```

The release is ready to submit when the script reports four `PASS` checks and `Phase 11 deployment verification complete`. The final submission should include:

- GitHub repository: `https://github.com/rupeshca007/wind-forecast-decision-support`
- Live dashboard: `https://wellfound-wind-dashboard.onrender.com`
- A short note describing the forecast-selection assumption and the January 2026 scope.

## Forecast-selection rule

The assignment does not specify an exact market gate-closure time. To avoid look-ahead bias, the first version will use this explicit, configurable assumption:

> For a delivery day `D`, select the forecast with the greatest `publishTime` that is less than or equal to `D - 1 day at 23:59:59 UTC`.

For every 30-minute `startTime` on delivery day `D`:

```text
eligible forecasts = forecasts where publishTime <= decision_cutoff(D)
selected forecast = eligible forecast with the latest publishTime
```

The default cutoff is only a working assumption, not a claim about the UK market timetable. The cutoff will be exposed as a configuration value so it can be changed if the company provides a different decision time.

Example:

```text
Delivery day:     2026-01-01
Default cutoff:   2025-12-31T23:59:59Z
```

Forecasts published after the cutoff will not be used for that delivery day. If no eligible forecast exists for an interval, the interval will be marked as missing rather than filled or interpolated.

## Data-quality rules

- Reject records with invalid timestamps or non-numeric generation values.
- Preserve raw API responses for reproducibility.
- Normalize timestamps before joining datasets.
- Join actuals and forecasts on normalized `startTime`.
- Track unmatched actual and forecast intervals.
- Do not silently fabricate missing values.
- If duplicate records exist, use the latest valid revision when a publication timestamp is available and report the deduplication count.

## Accuracy outputs

The dashboard will calculate and expose:

- Signed error: `forecast - actual`
- Absolute error: `abs(forecast - actual)`
- Mean absolute error (MAE)
- Root mean squared error (RMSE)
- Mean bias
- Weighted absolute percentage error (WAPE)
- 95th-percentile absolute error
- Matched, missing, and invalid interval counts

MAPE will not be the primary metric because percentage error becomes unstable when actual wind generation is close to zero.

## Phase 1 acceptance criteria

Phase 1 is complete when:

- The January 2026 delivery window is unambiguous.
- The actual and forecast datasets and required fields are documented.
- The forecast revision-selection rule is explicit and prevents future-data leakage.
- UTC handling is defined.
- Missing and duplicate data behavior is defined.
- Out-of-scope data and functionality are recorded.
- The remaining implementation can proceed without making new business assumptions.

## Planned product behavior

The completed dashboard will allow a user to:

1. Select a January 2026 delivery range.
2. Select or review the decision cutoff.
3. Compare forecast wind generation with actual wind generation.
4. Inspect forecast error by interval and day.
5. Review aggregate accuracy metrics and data-quality counts.

## External references

- [Elexon API developer portal](https://developer.data.elexon.co.uk/)
- [Elexon actual generation documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Elexon wind forecast documentation](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
