from __future__ import annotations

import math
from typing import Any


TRAFFIC_CONTROL_CAUSE_KEYWORDS = {
    "accident",
    "breakdown",
    "construction",
    "flood",
    "gathering",
    "pothole",
    "pot_hole",
    "pot holes",
    "procession",
    "protest",
    "rain",
    "rally",
    "roadwork",
    "vip",
    "water",
    "water_logging",
    "waterlogging",
}

CLOSURE_CAUSE_KEYWORDS = {
    "closure",
    "construction",
    "flood",
    "procession",
    "protest",
    "rally",
    "roadwork",
    "vip",
    "waterlogging",
}


def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    return str(value).strip().lower() in {"true", "t", "yes", "y", "1", "high"}


def text_contains_keyword(value: Any, keywords: set[str]) -> bool:
    text = str(value or "").strip().lower().replace("-", "_")
    if not text:
        return False
    return any(keyword in text for keyword in keywords)


def event_has_keyword(event_context: dict[str, Any], keywords: set[str]) -> bool:
    return any(
        text_contains_keyword(event_context.get(field), keywords)
        for field in ("event_cause", "event_type", "description", "priority")
    )


def is_high_priority(event_context: dict[str, Any]) -> bool:
    value = str(event_context.get("priority") or "").strip().lower()
    return value in {"high", "critical", "urgent", "p1", "1"}


def is_high_severity(event_context: dict[str, Any]) -> bool:
    return str(event_context.get("severity_label", "")).upper() == "HIGH"


def infer_requires_road_closure(event_context: dict[str, Any]) -> bool:
    explicit_closure = event_context.get("requires_road_closure")
    if truthy(explicit_closure):
        return True
    if explicit_closure is not None:
        return False
    return is_high_severity(event_context) and event_has_keyword(
        event_context,
        CLOSURE_CAUSE_KEYWORDS,
    )


def infer_requires_traffic_control(event_context: dict[str, Any]) -> bool:
    risk_score = float(event_context.get("risk_score") or 0.0)
    return (
        infer_requires_road_closure(event_context)
        or is_high_severity(event_context)
        or is_high_priority(event_context)
        or risk_score >= 0.5
        or event_has_keyword(event_context, TRAFFIC_CONTROL_CAUSE_KEYWORDS)
    )


def size_control_point(
    control_point: dict[str, Any],
    event_context: dict[str, Any],
) -> dict[str, Any]:
    lane_estimate = int(control_point.get("lane_estimate") or 1)
    requires_closure = infer_requires_road_closure(event_context)
    requires_traffic_control = infer_requires_traffic_control(event_context)
    risk_score = float(event_context.get("risk_score") or 0.0)
    is_arterial = bool(control_point.get("is_arterial"))

    personnel_needed = 2
    reasoning = ["base staffing: 2 officers"]

    # Wider or more complex junctions need one additional officer to split flow.
    if lane_estimate >= 3:
        personnel_needed += 1
        reasoning.append("lane_estimate >= 3: +1 officer")

    if requires_traffic_control and not requires_closure:
        personnel_needed += 1
        reasoning.append("traffic-control event: +1 officer")

    # Full closure needs extra hands for hard stops, cones, and hand-signaling.
    if requires_closure:
        personnel_needed += 2
        reasoning.append("requires_road_closure: +2 officers")

    if is_arterial and (requires_traffic_control or risk_score > 0.6):
        personnel_needed += 1
        reasoning.append("arterial control point: +1 officer")

    # High historical corridor/hour density adds one officer for queue spillback.
    if risk_score > 0.7:
        personnel_needed += 1
        reasoning.append("risk_score > 0.7: +1 officer")

    if requires_closure:
        barricades_needed = lane_estimate
        reasoning.append(f"barricades: 1 per estimated lane = {barricades_needed}")
    elif requires_traffic_control:
        barricades_needed = max(1, math.ceil(lane_estimate / 2))
        reasoning.append(
            f"barricades: partial traffic control = {barricades_needed}"
        )
    else:
        barricades_needed = 0
        reasoning.append("barricades: 0 because no closure is required")

    sized = dict(control_point)
    sized.update(
        {
            "requires_road_closure": requires_closure,
            "requires_traffic_control": requires_traffic_control,
            "personnel_needed": personnel_needed,
            "barricades_needed": barricades_needed,
            "reasoning": reasoning,
        }
    )
    return sized


def size_event_resources(
    control_points: list[dict[str, Any]],
    event_context: dict[str, Any],
) -> dict[str, Any]:
    sized_points = [
        size_control_point(control_point, event_context)
        for control_point in control_points
    ]
    return {
        "control_points": sized_points,
        "total_personnel": sum(point["personnel_needed"] for point in sized_points),
        "total_barricades": sum(point["barricades_needed"] for point in sized_points),
    }
