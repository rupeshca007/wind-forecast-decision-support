"""Fetch, normalize, and persist the January 2026 analysis dataset."""

from __future__ import annotations

import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.services.data_normalizer import normalize_january_dataset  # noqa: E402
from backend.app.services.elexon_client import (  # noqa: E402
    fetch_forecast_buffer,
    fetch_january_actuals,
)


RAW_DIR = PROJECT_ROOT / "data" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
CSV_PATH = PROCESSED_DIR / "january_2026.csv"
METADATA_PATH = PROCESSED_DIR / "january_2026_metadata.json"

CSV_FIELDS = [
    "delivery_time",
    "delivery_date",
    "decision_cutoff",
    "actual_generation_mw",
    "actual_half_hour_count",
    "forecast_generation_mw",
    "forecast_publish_time",
    "forecast_lead_hours",
    "match_status",
]


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as output:
        json.dump(payload, output, indent=2)
        output.write("\n")


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    actuals = fetch_january_actuals()
    forecasts = fetch_forecast_buffer()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    write_json(RAW_DIR / "fuelhh_january.json", actuals)
    write_json(RAW_DIR / "windfor_buffer.json", forecasts)

    normalized_rows, metadata = normalize_january_dataset(actuals, forecasts)
    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "source": "Elexon Insights API",
        **metadata,
    }
    write_csv(CSV_PATH, normalized_rows)
    write_json(METADATA_PATH, metadata)

    print("January 2026 dataset fetched and normalized")
    print(f"Raw actual records: {len(actuals)}")
    print(f"Raw forecast records: {len(forecasts)}")
    print(f"Normalized hourly rows: {len(normalized_rows)}")
    print(f"Status counts: {metadata['status_counts']}")
    print(f"Processed CSV: {CSV_PATH}")
    print(f"Metadata: {METADATA_PATH}")


if __name__ == "__main__":
    main()
