from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from allocation import load_police_stations
from predict import predict_impact
from workflow import FIELD_STATUS_PATH, LOCAL_FEEDBACK_PATH, read_jsonl


def recent_feedback(days: int = 30) -> list[dict[str, Any]]:
    cutoff = datetime.now(UTC) - timedelta(days=days)
    rows = []
    for row in read_jsonl(LOCAL_FEEDBACK_PATH):
        created_at = row.get("created_at")
        if not created_at:
            continue
        try:
            created = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        except ValueError:
            continue
        if created >= cutoff:
            rows.append(row)
    return rows


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def forecast_error_by_category(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        predicted = safe_float(row.get("predicted_duration_minutes"))
        actual = safe_float(row.get("actual_duration_minutes"))
        if predicted <= 0 or actual <= 0:
            continue
        category = str(row.get("event_name") or row.get("predicted_severity") or "unknown")
        grouped[category].append(abs(predicted - actual) / actual * 100.0)

    return [
        {
            "category": category,
            "mape": round(sum(errors) / len(errors), 2),
            "sample_count": len(errors),
        }
        for category, errors in sorted(grouped.items(), key=lambda item: (-len(item[1]), item[0]))[:8]
    ]


def active_high_risk_corridors(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    corridors = {}
    for event in events:
        try:
            forecast = predict_impact(event)
        except Exception:
            continue
        if float(forecast.get("risk_score") or 0.0) <= 0.7:
            continue
        corridor = str(event.get("corridor") or "Unknown")
        current = corridors.setdefault(
            corridor,
            {
                "corridor": corridor,
                "risk_score": 0.0,
                "event_count": 0,
                "preventable": True,
            },
        )
        current["risk_score"] = max(current["risk_score"], round(float(forecast["risk_score"]), 3))
        current["event_count"] += 1
    return sorted(corridors.values(), key=lambda row: row["risk_score"], reverse=True)


def executive_roi_summary(
    active_events: list[dict[str, Any]],
    planned_events: list[dict[str, Any]],
) -> dict[str, Any]:
    rows = recent_feedback()
    accepted_rows = [row for row in rows if row.get("plan_accepted") is True]
    predicted_actual_pairs = [
        (
            safe_float(row.get("predicted_duration_minutes")),
            safe_float(row.get("actual_duration_minutes")),
        )
        for row in rows
        if safe_float(row.get("predicted_duration_minutes")) > 0
        and safe_float(row.get("actual_duration_minutes")) > 0
    ]
    reductions = [
        max(predicted - actual, 0.0)
        for predicted, actual in predicted_actual_pairs
    ]
    average_duration_reduction = (
        sum(reductions) / len(reductions)
        if reductions
        else 0.0
    )
    plan_acceptance_rate = len(accepted_rows) / len(rows) if rows else 0.0
    deployed_personnel = sum(
        int(row.get("adjusted_personnel") or row.get("plan_total_personnel") or 0)
        for row in accepted_rows
    )
    station_capacity = sum(int(station.get("available_personnel") or 0) for station in load_police_stations())
    personnel_utilization = deployed_personnel / max(station_capacity, 1)
    high_risk_corridors = active_high_risk_corridors([*active_events, *planned_events])
    delay_hours_avoided = sum(reductions) * 110.0 / 60.0
    field_status_rows = read_jsonl(FIELD_STATUS_PATH)
    closure_updates = [
        row for row in field_status_rows if row.get("status") in {"road_cleared", "Road cleared"}
    ]
    closure_compliance_rate = len(closure_updates) / max(len(accepted_rows), 1) if accepted_rows else 0.0

    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "average_incident_duration_reduction_minutes": round(average_duration_reduction, 1),
        "deployment_time_saved_minutes": round(len(accepted_rows) * 12.0, 1),
        "personnel_utilization": round(min(personnel_utilization, 1.0), 3),
        "preventable_high_risk_corridors_detected": len(high_risk_corridors),
        "high_risk_corridors": high_risk_corridors[:6],
        "forecast_error_by_event_category": forecast_error_by_category(rows),
        "plan_acceptance_rate": round(plan_acceptance_rate, 3),
        "citizen_delay_hours_avoided": round(delay_hours_avoided, 1),
        "closure_compliance_rate": round(min(closure_compliance_rate, 1.0), 3),
        "average_reopening_time_minutes": None,
        "sample_count": len(rows),
        "method_notes": [
            "Duration reduction compares predicted duration to actual feedback duration.",
            "Delay-hours avoided estimates 110 affected road users per reduced incident minute.",
            "Deployment time saved uses a conservative 12 minute saving per accepted plan.",
        ],
    }
