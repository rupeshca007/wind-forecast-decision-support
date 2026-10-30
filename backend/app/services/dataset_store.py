"""Read-only access to the normalized January analysis dataset."""

from __future__ import annotations

import csv
import json
import os
from datetime import date
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_PATH = PROJECT_ROOT / "data" / "processed" / "january_2026.csv"
REQUIRED_COLUMNS = {
    "delivery_time",
    "delivery_date",
    "decision_cutoff",
    "actual_generation_mw",
    "actual_half_hour_count",
    "forecast_generation_mw",
    "forecast_publish_time",
    "forecast_lead_hours",
    "match_status",
}


class DatasetStore:
    """Load the normalized dataset once and serve filtered row copies."""

    def __init__(self, data_path: Path | None = None) -> None:
        configured_path = os.getenv("WIND_DATA_PATH")
        self.data_path = Path(configured_path) if configured_path else (data_path or DEFAULT_DATA_PATH)
        if not self.data_path.is_absolute():
            self.data_path = PROJECT_ROOT / self.data_path
        self.metadata_path = self.data_path.with_name(f"{self.data_path.stem}_metadata.json")
        self.rows: list[dict[str, str]] = []
        self.metadata: dict[str, Any] = {}
        self.error: str | None = None
        self.reload()

    @property
    def ready(self) -> bool:
        return self.error is None and bool(self.rows)

    def reload(self) -> None:
        """Load rows and metadata, retaining a useful error for API health checks."""

        self.rows = []
        self.metadata = {}
        self.error = None

        try:
            with self.data_path.open("r", encoding="utf-8", newline="") as source:
                reader = csv.DictReader(source)
                columns = set(reader.fieldnames or [])
                missing = REQUIRED_COLUMNS - columns
                if missing:
                    raise ValueError(f"dataset is missing columns: {sorted(missing)}")
                self.rows = [dict(row) for row in reader]
            if not self.rows:
                raise ValueError("dataset contains no rows")

            if self.metadata_path.exists():
                with self.metadata_path.open("r", encoding="utf-8") as source:
                    loaded = json.load(source)
                    if isinstance(loaded, dict):
                        self.metadata = loaded
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.error = str(error)

    def filter_rows(
        self,
        start: date | None = None,
        end: date | None = None,
    ) -> list[dict[str, str]]:
        """Return rows whose inclusive delivery date is within the requested range."""

        selected: list[dict[str, str]] = []
        for row in self.rows:
            delivery_date = date.fromisoformat(row["delivery_date"])
            if start is not None and delivery_date < start:
                continue
            if end is not None and delivery_date > end:
                continue
            selected.append(dict(row))
        return selected
