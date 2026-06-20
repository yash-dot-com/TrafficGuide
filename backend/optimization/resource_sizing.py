from __future__ import annotations

import math
from typing import Any

from backend.ml.feature_cleaning import event_category_for_cause


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
MAX_PERSONNEL_PER_POINT = 10
MAX_BARRICADES_PER_POINT = 18

CATEGORY_POINT_LIMITS = {
    "minor_road_defect": (1, 2, 2),
    "breakdown": (1, 2, 3),
    "crash": (2, 3, 4),
    "congestion": (1, 2, 3),
    "waterlogging": (2, 3, 5),
    "roadwork": (2, 3, 5),
    "obstruction": (2, 3, 4),
    "planned_crowd_event": (3, 3, 5),
    "vip_movement": (3, 5, 5),
    "weather_visibility": (1, 2, 3),
    "other": (1, 2, 4),
    "unknown": (1, 2, 4),
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


def event_category(event_context: dict[str, Any]) -> str:
    explicit = str(event_context.get("event_category") or "").strip()
    if explicit and explicit.upper() != "UNKNOWN":
        return explicit
    return event_category_for_cause(event_context.get("event_cause"))


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


def control_point_limit_for_event(event_context: dict[str, Any]) -> int:
    category = event_category(event_context)
    pressure = event_pressure(event_context)
    requires_closure = infer_requires_road_closure(event_context)
    risk_score = safe_float(event_context.get("risk_score"))
    queue_length_m = safe_float(event_context.get("queue_length_m"))
    expected_delay = safe_float(event_context.get("expected_delay_minutes"))
    duration_median = safe_float(event_context.get("duration_median"))
    low_limit, medium_limit, high_limit = CATEGORY_POINT_LIMITS.get(category, CATEGORY_POINT_LIMITS["other"])

    high_intensity = (
        requires_closure
        or is_high_severity(event_context)
        or pressure >= 0.68
        or risk_score >= 0.72
        or queue_length_m >= 650
        or expected_delay >= 120
    )
    medium_intensity = (
        high_intensity
        or is_high_priority(event_context)
        or pressure >= 0.38
        or risk_score >= 0.45
        or queue_length_m >= 300
        or expected_delay >= 60
        or duration_median >= 100
    )

    if high_intensity:
        return high_limit
    if medium_intensity:
        return medium_limit
    return low_limit


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def event_pressure(event_context: dict[str, Any]) -> float:
    risk_score = safe_float(event_context.get("risk_score"))
    severity_probability = safe_float(event_context.get("severity_probability"))
    queue_length_m = safe_float(event_context.get("queue_length_m"))
    expected_delay = safe_float(event_context.get("expected_delay_minutes"))
    duration_median = safe_float(event_context.get("duration_median"))
    pressure = (
        risk_score * 0.32
        + severity_probability * 0.28
        + min(queue_length_m / 900.0, 1.0) * 0.22
        + min(expected_delay / 180.0, 1.0) * 0.12
        + min(duration_median / 360.0, 1.0) * 0.06
    )
    return max(0.0, min(1.0, pressure))


def barricade_strategy(
    lane_estimate: int,
    requires_closure: bool,
    requires_traffic_control: bool,
    pressure: float,
    is_arterial: bool,
) -> dict[str, Any]:
    if requires_closure:
        placement = "hard_perimeter_with_tapered_approaches"
        emergency_access = "keep one signed emergency-access lane open where road width permits"
        isolation_radius_m = 180 + int(pressure * 220)
        spillover_buffer_m = 90 + lane_estimate * 25
    elif requires_traffic_control:
        placement = "partial_filter_points_with_upstream_warning"
        emergency_access = "do not block kerbside emergency access; use movable barricades"
        isolation_radius_m = 90 + int(pressure * 140)
        spillover_buffer_m = 45 + lane_estimate * 18
    else:
        placement = "monitor_only"
        emergency_access = "no fixed barricade footprint"
        isolation_radius_m = 0
        spillover_buffer_m = 0

    if is_arterial and placement != "monitor_only":
        spillover_buffer_m += 45

    return {
        "placement": placement,
        "emergency_access": emergency_access,
        "isolation_radius_m": isolation_radius_m,
        "spillover_buffer_m": spillover_buffer_m,
    }


def category_barricade_strategy(
    category: str,
    lane_estimate: int,
    pressure: float,
    is_arterial: bool,
) -> dict[str, Any]:
    if category == "minor_road_defect":
        return {
            "placement": "localized_hazard_taper_with_warning_cones",
            "emergency_access": "keep all through lanes recoverable; use movable cones and one response vehicle as buffer",
            "isolation_radius_m": 35 + int(pressure * 45),
            "spillover_buffer_m": 20 + lane_estimate * 8 + (20 if is_arterial else 0),
        }
    if category == "breakdown":
        return {
            "placement": "shoulder_or_lane_taper_around_disabled_vehicle",
            "emergency_access": "maintain one tow-access lane and avoid hard closure unless crash risk escalates",
            "isolation_radius_m": 55 + int(pressure * 70),
            "spillover_buffer_m": 35 + lane_estimate * 12 + (25 if is_arterial else 0),
        }
    if category == "crash":
        return {
            "placement": "incident_scene_protection_with_upstream_taper",
            "emergency_access": "reserve ambulance and tow approach lane before placing hard stops",
            "isolation_radius_m": 90 + int(pressure * 130),
            "spillover_buffer_m": 55 + lane_estimate * 18 + (35 if is_arterial else 0),
        }
    if category == "waterlogging":
        return {
            "placement": "flooded_lane_filter_with_depth_warning",
            "emergency_access": "keep dry high-ground side accessible for emergency vehicles",
            "isolation_radius_m": 100 + int(pressure * 160),
            "spillover_buffer_m": 65 + lane_estimate * 20 + (45 if is_arterial else 0),
        }
    if category == "obstruction":
        return {
            "placement": "obstruction_perimeter_with_upstream_taper",
            "emergency_access": "leave utility and emergency clearing access through the least affected side",
            "isolation_radius_m": 80 + int(pressure * 120),
            "spillover_buffer_m": 50 + lane_estimate * 16 + (35 if is_arterial else 0),
        }
    if category == "roadwork":
        return {
            "placement": "work-zone_taper_with_signed_lane_filter",
            "emergency_access": "preserve contractor and emergency vehicle entry through one controlled approach",
            "isolation_radius_m": 110 + int(pressure * 150),
            "spillover_buffer_m": 70 + lane_estimate * 18 + (40 if is_arterial else 0),
        }
    if category == "planned_crowd_event":
        return {
            "placement": "crowd_route_filter_points_with_pedestrian_buffer",
            "emergency_access": "keep one cross-corridor emergency route unblocked and staffed",
            "isolation_radius_m": 130 + int(pressure * 170),
            "spillover_buffer_m": 80 + lane_estimate * 18 + (45 if is_arterial else 0),
        }
    if category == "vip_movement":
        return {
            "placement": "time-boxed_vip_corridor_filter_with_rolling_release",
            "emergency_access": "avoid static hard closure outside the active movement window",
            "isolation_radius_m": 150 + int(pressure * 180),
            "spillover_buffer_m": 90 + lane_estimate * 20 + (50 if is_arterial else 0),
        }
    if category in {"congestion", "weather_visibility"}:
        return {
            "placement": "flow_metering_and_warning_points",
            "emergency_access": "do not add fixed barriers unless visibility or queue spillback worsens",
            "isolation_radius_m": 45 + int(pressure * 80),
            "spillover_buffer_m": 30 + lane_estimate * 10 + (20 if is_arterial else 0),
        }
    return {}


def category_specific_sizing(
    category: str,
    lane_estimate: int,
    pressure: float,
    risk_score: float,
    is_arterial: bool,
    requires_closure: bool,
    requires_traffic_control: bool,
) -> tuple[int, int, list[str], dict[str, Any]] | None:
    if requires_closure:
        return None

    if category == "minor_road_defect":
        personnel = 2
        reasoning = ["localized road-defect hazard: 2 officers"]
        if lane_estimate >= 4 or is_arterial:
            personnel += 1
            reasoning.append("wide/arterial approach: +1 officer")
        if pressure > 0.75 or risk_score > 0.8:
            personnel += 1
            reasoning.append("high pressure/risk: +1 officer")
        barricades = 0
        if requires_traffic_control:
            barricades = max(1, min(3, math.ceil(lane_estimate / 3)))
            reasoning.append(f"movable warning cones/barricades: {barricades}")
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "breakdown":
        personnel = 2
        reasoning = ["disabled-vehicle response: 2 officers"]
        if lane_estimate >= 3:
            personnel += 1
            reasoning.append("multi-lane approach: +1 officer")
        if is_arterial or pressure > 0.65:
            personnel += 1
            reasoning.append("arterial/high pressure: +1 officer")
        barricades = max(1, min(4, math.ceil(lane_estimate / 2))) if requires_traffic_control else 0
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "crash":
        personnel = 3
        reasoning = ["crash-scene protection: 3 officers"]
        if lane_estimate >= 4:
            personnel += 1
            reasoning.append("wide crash approach: +1 officer")
        if (is_arterial and (risk_score > 0.35 or pressure > 0.45)) or risk_score > 0.65:
            personnel += 1
            reasoning.append("arterial/high-risk corridor: +1 officer")
        if pressure > 0.78:
            personnel += 1
            reasoning.append("high event pressure: +1 officer")
        barricades = max(2, min(6, math.ceil(lane_estimate / 2) + 1))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "waterlogging":
        personnel = 2
        reasoning = ["waterlogging lane-filter control: 2 officers"]
        if lane_estimate >= 3:
            personnel += 1
            reasoning.append("multi-lane approach: +1 officer")
        if is_arterial and (pressure > 0.4 or risk_score > 0.4):
            personnel += 1
            reasoning.append("arterial with elevated pressure/risk: +1 officer")
        if pressure > 0.65 or risk_score > 0.65:
            personnel += 1
            reasoning.append("high pressure/risk flood control: +1 officer")
        barricades = max(1, min(5, math.ceil(lane_estimate / 2) + (1 if pressure > 0.6 else 0)))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "obstruction":
        personnel = 3
        reasoning = ["road obstruction control: 3 officers"]
        if lane_estimate >= 3:
            personnel += 1
            reasoning.append("multi-lane approach: +1 officer")
        if is_arterial or pressure > 0.7:
            personnel += 1
            reasoning.append("arterial/high pressure: +1 officer")
        barricades = max(2, min(6, math.ceil(lane_estimate / 2) + 1))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "roadwork":
        personnel = 3
        reasoning = ["work-zone traffic filter: 3 officers"]
        if lane_estimate >= 3:
            personnel += 1
            reasoning.append("multi-lane work zone: +1 officer")
        if is_arterial:
            personnel += 1
            reasoning.append("arterial work zone: +1 officer")
        if pressure > 0.75:
            personnel += 1
            reasoning.append("high event pressure: +1 officer")
        barricades = max(3, min(8, lane_estimate + 1))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "planned_crowd_event":
        personnel = 3
        reasoning = ["crowd/event route filter: 3 officers"]
        if lane_estimate >= 3:
            personnel += 1
            reasoning.append("multi-lane crowd route: +1 officer")
        if is_arterial and (risk_score > 0.45 or pressure > 0.45):
            personnel += 1
            reasoning.append("arterial crowd route with elevated risk/pressure: +1 officer")
        elif risk_score > 0.6:
            personnel += 1
            reasoning.append("high-risk crowd route: +1 officer")
        if pressure > 0.78:
            personnel += 1
            reasoning.append("high event pressure: +1 officer")
        barricades = max(3, min(8, math.ceil(lane_estimate / 2) + 2))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category == "vip_movement":
        personnel = 4
        reasoning = ["VIP movement rolling filter: 4 officers"]
        if lane_estimate >= 4:
            personnel += 1
            reasoning.append("wide approach: +1 officer")
        if is_arterial:
            personnel += 1
            reasoning.append("arterial movement corridor: +1 officer")
        barricades = max(2, min(6, math.ceil(lane_estimate / 2) + 1))
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    if category in {"congestion", "weather_visibility"}:
        personnel = 2
        reasoning = [f"{category} flow-metering: 2 officers"]
        if lane_estimate >= 4 or is_arterial:
            personnel += 1
            reasoning.append("wide/arterial approach: +1 officer")
        if risk_score > 0.7:
            personnel += 1
            reasoning.append("high corridor/hour risk: +1 officer")
        if pressure > 0.75:
            personnel += 1
            reasoning.append("high event pressure: +1 officer")
        barricades = max(1, min(3, math.ceil(lane_estimate / 3))) if requires_traffic_control else 0
        return (
            personnel,
            barricades,
            reasoning,
            category_barricade_strategy(category, lane_estimate, pressure, is_arterial),
        )

    return None


def size_control_point(
    control_point: dict[str, Any],
    event_context: dict[str, Any],
) -> dict[str, Any]:
    lane_estimate = int(control_point.get("lane_estimate") or 1)
    requires_closure = infer_requires_road_closure(event_context)
    requires_traffic_control = infer_requires_traffic_control(event_context)
    risk_score = float(event_context.get("risk_score") or 0.0)
    is_arterial = bool(control_point.get("is_arterial"))
    pressure = event_pressure(event_context)
    category = event_category(event_context)

    category_sizing = category_specific_sizing(
        category,
        lane_estimate,
        pressure,
        risk_score,
        is_arterial,
        requires_closure,
        requires_traffic_control,
    )
    if category_sizing is not None:
        personnel_needed, barricades_needed, reasoning, strategy = category_sizing
        personnel_needed = min(personnel_needed, MAX_PERSONNEL_PER_POINT)
        barricades_needed = min(barricades_needed, MAX_BARRICADES_PER_POINT)
        sized = dict(control_point)
        sized.update(
            {
                "event_category": category,
                "requires_road_closure": requires_closure,
                "requires_traffic_control": requires_traffic_control,
                "event_pressure": round(pressure, 3),
                "personnel_needed": personnel_needed,
                "barricades_needed": barricades_needed,
                "barricade_strategy": strategy,
                "reasoning": reasoning,
            }
        )
        return sized

    personnel_needed = 2
    reasoning = [f"{category} base staffing: 2 officers"]

    # Wider or more complex junctions need one additional officer to split flow.
    if lane_estimate >= 3:
        personnel_needed += 1
        reasoning.append("lane_estimate >= 3: +1 officer")

    if requires_traffic_control and not requires_closure:
        personnel_needed += 1
        reasoning.append("traffic-control event: +1 officer")

    if pressure > 0.55:
        personnel_needed += 1
        reasoning.append("event pressure > 0.55: +1 officer")

    if pressure > 0.78:
        personnel_needed += 1
        reasoning.append("event pressure > 0.78: +1 officer")

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
        barricades_needed = lane_estimate + 2
        if pressure > 0.65:
            barricades_needed += 2
            reasoning.append("barricades: high pressure adds upstream taper")
        reasoning.append(f"barricades: closure perimeter by lane = {barricades_needed}")
    elif requires_traffic_control:
        barricades_needed = max(1, math.ceil(lane_estimate / 2))
        if pressure > 0.65:
            barricades_needed += 1
        reasoning.append(
            f"barricades: partial traffic control = {barricades_needed}"
        )
    else:
        barricades_needed = 0
        reasoning.append("barricades: 0 because no closure is required")

    personnel_needed = min(personnel_needed, MAX_PERSONNEL_PER_POINT)
    barricades_needed = min(barricades_needed, MAX_BARRICADES_PER_POINT)
    strategy = barricade_strategy(
        lane_estimate,
        requires_closure,
        requires_traffic_control,
        pressure,
        is_arterial,
    )

    sized = dict(control_point)
    sized.update(
        {
            "requires_road_closure": requires_closure,
            "requires_traffic_control": requires_traffic_control,
            "event_category": category,
            "event_pressure": round(pressure, 3),
            "personnel_needed": personnel_needed,
            "barricades_needed": barricades_needed,
            "barricade_strategy": strategy,
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
