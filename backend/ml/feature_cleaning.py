from __future__ import annotations

from typing import Any

import pandas as pd


NULL_SENTINELS = {"", "null", "none", "nan", "nat", "n/a", "na"}

CAUSE_ALIASES = {
    "accidents": "accident",
    "crash": "accident",
    "collision": "accident",
    "vehicle_accident": "accident",
    "vehicle breakdown": "vehicle_breakdown",
    "pot_holes": "pothole",
    "pot holes": "pothole",
    "pot-hole": "pothole",
    "pot_hole": "pothole",
    "potholes": "pothole",
    "road_conditions": "road_condition",
    "road condition": "road_condition",
    "road_conditions_bad": "road_condition",
    "bad road": "road_condition",
    "tree fall": "tree_fall",
    "tree_fallen": "tree_fall",
    "water logging": "water_logging",
    "water-logging": "water_logging",
    "waterlogging": "water_logging",
    "flood": "water_logging",
    "flooding": "water_logging",
    "rain_water": "water_logging",
    "rain water": "water_logging",
    "road work": "construction",
    "road_work": "construction",
    "roadwork": "construction",
    "metro_work": "construction",
    "metro construction": "construction",
    "civil_work": "construction",
    "public event": "public_event",
    "public gathering": "public_event",
    "festival": "public_event",
    "sports_event": "public_event",
    "match": "public_event",
    "rally": "procession",
    "political_rally": "procession",
    "march": "procession",
    "vip movement": "vip_movement",
    "vip": "vip_movement",
    "fog": "low_visibility",
    "fog / low visibility": "low_visibility",
    "low visibility": "low_visibility",
}

MINOR_ROAD_DEFECT_CAUSES = {
    "pothole",
    "road_condition",
    "road_defect",
    "bad_road",
}

EVENT_CATEGORY_BY_CAUSE = {
    "accident": "crash",
    "vehicle_breakdown": "breakdown",
    "pothole": "minor_road_defect",
    "road_condition": "minor_road_defect",
    "road_defect": "minor_road_defect",
    "bad_road": "minor_road_defect",
    "construction": "roadwork",
    "water_logging": "waterlogging",
    "tree_fall": "obstruction",
    "debris": "obstruction",
    "congestion": "congestion",
    "public_event": "planned_crowd_event",
    "procession": "planned_crowd_event",
    "protest": "planned_crowd_event",
    "vip_movement": "vip_movement",
    "low_visibility": "weather_visibility",
}

EVENT_CATEGORY_CAP_MINUTES = {
    "crash": 360,
    "breakdown": 360,
    "minor_road_defect": 360,
    "roadwork": 720,
    "waterlogging": 720,
    "obstruction": 720,
    "congestion": 240,
    "planned_crowd_event": 720,
    "vip_movement": 360,
    "weather_visibility": 360,
}


def is_missing(value: Any) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def normalize_category(value: Any) -> str:
    if is_missing(value):
        return "UNKNOWN"

    normalized = str(value).strip()
    if normalized.lower() in NULL_SENTINELS:
        return "UNKNOWN"
    return normalized


def normalize_event_cause(value: Any) -> str:
    normalized = normalize_category(value)
    if normalized == "UNKNOWN":
        return normalized

    key = normalized.strip().lower().replace("-", "_")
    key = " ".join(key.replace("_", " ").split())
    lookup_keys = {
        key,
        key.replace(" ", "_"),
        key.replace(" ", "-"),
    }
    for lookup_key in lookup_keys:
        if lookup_key in CAUSE_ALIASES:
            return CAUSE_ALIASES[lookup_key]
    return normalized.strip().lower().replace(" ", "_")


def event_category_for_cause(value: Any) -> str:
    cause = normalize_event_cause(value)
    if cause in EVENT_CATEGORY_BY_CAUSE:
        return EVENT_CATEGORY_BY_CAUSE[cause]
    if cause == "UNKNOWN":
        return "unknown"
    if "accident" in cause or "crash" in cause or "collision" in cause:
        return "crash"
    if "breakdown" in cause:
        return "breakdown"
    if "water" in cause or "flood" in cause or "rain" in cause:
        return "waterlogging"
    if "construction" in cause or "roadwork" in cause or "road_work" in cause:
        return "roadwork"
    if "tree" in cause or "debris" in cause or "obstruction" in cause:
        return "obstruction"
    if "procession" in cause or "protest" in cause or "event" in cause or "rally" in cause:
        return "planned_crowd_event"
    if "vip" in cause:
        return "vip_movement"
    if "fog" in cause or "visibility" in cause:
        return "weather_visibility"
    return "other"


def event_text_values(event_context: dict[str, Any]) -> list[str]:
    return [
        str(event_context.get(field) or "").strip().lower().replace("-", "_")
        for field in ("event_cause", "event_type", "description", "priority")
    ]


def is_minor_road_defect_context(event_context: dict[str, Any]) -> bool:
    cause = normalize_event_cause(event_context.get("event_cause"))
    if cause in MINOR_ROAD_DEFECT_CAUSES:
        return True
    if event_category_for_cause(cause) == "minor_road_defect":
        return True
    text = " ".join(event_text_values(event_context))
    return any(keyword in text for keyword in MINOR_ROAD_DEFECT_CAUSES)


def duration_cap_for_event(event_context: dict[str, Any], default_minutes: int) -> int:
    category = event_context.get("event_category")
    if not category or normalize_category(category) == "UNKNOWN":
        category = event_category_for_cause(event_context.get("event_cause"))
    cap = EVENT_CATEGORY_CAP_MINUTES.get(str(category), default_minutes)
    return min(default_minutes, cap)
