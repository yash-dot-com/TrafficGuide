from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from integrations import weather_feed


APP_ROOT = Path(__file__).resolve().parent
TRAINING_CACHE = APP_ROOT / "models" / "training_events_preprocessed.parquet"


def load_training_frame() -> pd.DataFrame:
    if not TRAINING_CACHE.exists():
        return pd.DataFrame()
    return pd.read_parquet(TRAINING_CACHE)


def day_part(hour: int) -> str:
    if 6 <= hour < 11:
        return "morning_peak"
    if 11 <= hour < 16:
        return "midday"
    if 16 <= hour < 21:
        return "evening_peak"
    return "night"


def grouped_duration_summary(frame: pd.DataFrame, by: str, limit: int = 8) -> list[dict[str, Any]]:
    if frame.empty or by not in frame:
        return []
    data = frame.copy()
    data["duration_available"] = data["duration_minutes"].notna() & (data["duration_minutes"] >= 0)
    grouped = (
        data.groupby(by, dropna=False)
        .agg(
            rows=("id", "count"),
            duration_coverage=("duration_available", "mean"),
            median_duration_minutes=("duration_minutes", "median"),
            closure_rate=("requires_road_closure", "mean"),
        )
        .reset_index()
        .sort_values("rows", ascending=False)
        .head(limit)
    )
    return [
        {
            "segment": str(row[by]),
            "rows": int(row["rows"]),
            "duration_coverage": round(float(row["duration_coverage"] or 0.0), 3),
            "median_duration_minutes": None
            if pd.isna(row["median_duration_minutes"])
            else round(float(row["median_duration_minutes"]), 1),
            "closure_rate": None
            if pd.isna(row["closure_rate"])
            else round(float(row["closure_rate"]), 3),
        }
        for _, row in grouped.iterrows()
    ]


def forecast_backtest_summary() -> dict[str, Any]:
    frame = load_training_frame()
    if frame.empty:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "missing_training_cache",
            "message": "Run python train_models.py to generate training_events_preprocessed.parquet.",
            "segments": {},
        }

    data = frame.copy()
    data["time_of_day"] = data["hour_of_day"].map(day_part)
    observed = data["duration_minutes"].notna() & (data["duration_minutes"] >= 0)
    weather = weather_feed()
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ok",
        "rows": int(len(data)),
        "right_censored_rows": int((~observed).sum()),
        "duration_coverage": round(float(observed.mean()), 3),
        "weather_segment": weather.get("rainfall_intensity", "unknown"),
        "segments": {
            "by_corridor": grouped_duration_summary(data, "corridor"),
            "by_event_type": grouped_duration_summary(data, "event_cause"),
            "by_time_of_day": grouped_duration_summary(data, "time_of_day"),
            "by_weather": [
                {
                    "segment": weather.get("rainfall_intensity", "unknown"),
                    "rainfall_mm_1h": weather.get("rainfall_mm_1h"),
                    "flood_risk": weather.get("flood_risk"),
                    "note": "Weather feed is joined at scoring time; historical weather archive is the next production connector.",
                }
            ],
        },
    }


def drift_summary(current_events: list[dict[str, Any]]) -> dict[str, Any]:
    frame = load_training_frame()
    if frame.empty:
        return {
            "generated_at": datetime.now(UTC).isoformat(),
            "status": "missing_training_cache",
            "drift_score": None,
            "retrain_recommended": False,
        }

    baseline_causes = {str(value).lower() for value in frame["event_cause"].dropna().unique()}
    baseline_corridors = {str(value).lower() for value in frame["corridor"].dropna().unique()}
    current_causes = [str(event.get("event_cause", "")).lower() for event in current_events]
    current_corridors = [str(event.get("corridor", "")).lower() for event in current_events]
    total = max(len(current_events), 1)
    unseen_cause_share = sum(cause not in baseline_causes for cause in current_causes) / total
    unseen_corridor_share = sum(corridor not in baseline_corridors for corridor in current_corridors) / total
    drift_score = round((unseen_cause_share * 0.55 + unseen_corridor_share * 0.45), 3)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "ok",
        "drift_score": drift_score,
        "unseen_event_cause_share": round(unseen_cause_share, 3),
        "unseen_corridor_share": round(unseen_corridor_share, 3),
        "retrain_recommended": drift_score > 0.2,
        "next_retrain_window": "02:00 IST daily",
        "monitored_events": len(current_events),
    }


def retrain_plan() -> dict[str, Any]:
    return {
        "mode": "operator_approved",
        "command": "python train_models.py",
        "schedule": "02:00 IST daily when drift_score > 0.2 or new labeled feedback >= 100 rows",
        "safety": [
            "train into a candidate models directory",
            "run backtest and drift checks",
            "promote artifacts only after commander/admin approval",
        ],
    }
