from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from allocation import load_police_stations
from generate_plan import generate_deployment_plan
from predict import predict_impact
from road_graph import get_graph


@dataclass(frozen=True)
class ScenarioProfile:
    name: str
    control_radius_m: float
    allocation_radius_m: float
    force_closure_for_high: bool
    operating_posture: str


SCENARIOS = {
    "minimal": ScenarioProfile(
        name="minimal",
        control_radius_m=650.0,
        allocation_radius_m=4_000.0,
        force_closure_for_high=False,
        operating_posture="hold traffic with the smallest local footprint",
    ),
    "recommended": ScenarioProfile(
        name="recommended",
        control_radius_m=1_000.0,
        allocation_radius_m=6_000.0,
        force_closure_for_high=False,
        operating_posture="balance clearance speed with station coverage",
    ),
    "aggressive": ScenarioProfile(
        name="aggressive",
        control_radius_m=1_400.0,
        allocation_radius_m=8_000.0,
        force_closure_for_high=True,
        operating_posture="pre-empt spillback with wider closures and more control points",
    ),
}


def shift_multiplier(now: datetime | None = None) -> float:
    current = now or datetime.now()
    hour = current.hour
    if 7 <= hour < 11 or 16 <= hour < 21:
        return 0.82
    if 22 <= hour or hour < 6:
        return 0.62
    return 0.74


def station_constraint_rows() -> list[dict[str, Any]]:
    multiplier = shift_multiplier()
    constraints = []
    for station in load_police_stations():
        available_personnel = int(station.get("available_personnel") or 0)
        available_barricades = int(station.get("available_barricades") or 0)
        constraints.append(
            {
                **station,
                "shift_available_personnel": int(available_personnel * multiplier),
                "senior_officers": max(1, available_personnel // 8),
                "tow_trucks": max(1, available_personnel // 18),
                "ambulances": 1 if available_personnel >= 20 else 0,
                "cones": available_barricades * 6,
                "portable_signs": max(2, available_barricades // 6),
                "jurisdiction": station.get("zone"),
            }
        )
    return constraints


def scenario_event_features(
    event: dict[str, Any],
    forecast: dict[str, Any],
    profile: ScenarioProfile,
) -> dict[str, Any]:
    merged = dict(event)
    merged.update(forecast)
    if profile.force_closure_for_high and forecast.get("severity_label") == "HIGH":
        merged["requires_road_closure"] = True
    return merged


def add_travel_time_to_allocations(plan: dict[str, Any]) -> None:
    risk_score = float(plan.get("event", {}).get("risk_score") or 0.0)
    response_speed_kmph = max(12.0, 28.0 - risk_score * 10.0)
    for allocation in plan.get("allocations", []):
        distance_m = float(allocation.get("distance_m") or 0.0)
        allocation["estimated_travel_time_minutes"] = round(
            distance_m / (response_speed_kmph * 1000.0 / 60.0),
            1,
        )


def station_usage(plans: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    usage: dict[str, dict[str, Any]] = {}
    for plan in plans:
        for allocation in plan.get("allocations", []):
            station_name = str(allocation.get("station_name") or "Unknown")
            row = usage.setdefault(
                station_name,
                {
                    "station_name": station_name,
                    "personnel_assigned": 0,
                    "events": set(),
                    "max_travel_time_minutes": 0.0,
                },
            )
            row["personnel_assigned"] += int(allocation.get("personnel_assigned") or 0)
            row["events"].add(str(plan.get("event_id") or "unknown"))
            row["max_travel_time_minutes"] = max(
                float(row["max_travel_time_minutes"]),
                float(allocation.get("estimated_travel_time_minutes") or 0.0),
            )

    for row in usage.values():
        row["events"] = sorted(row["events"])
    return usage


def constraint_summary(plans: list[dict[str, Any]]) -> dict[str, Any]:
    constraints = station_constraint_rows()
    constraint_by_name = {str(row["name"]): row for row in constraints}
    usage = station_usage(plans)
    violations = []
    for station_name, row in usage.items():
        constraint = constraint_by_name.get(station_name)
        if not constraint:
            continue
        overage = int(row["personnel_assigned"]) - int(constraint["shift_available_personnel"])
        if overage > 0:
            violations.append(
                {
                    "station_name": station_name,
                    "type": "shift_personnel_shortfall",
                    "shortfall": overage,
                    "assigned": row["personnel_assigned"],
                    "shift_available": constraint["shift_available_personnel"],
                }
            )

    total_barricades = sum(int(plan.get("total_barricades") or 0) for plan in plans)
    total_inventory_barricades = sum(int(row.get("available_barricades") or 0) for row in constraints)
    if total_barricades > total_inventory_barricades:
        violations.append(
            {
                "type": "barricade_inventory_shortfall",
                "shortfall": total_barricades - total_inventory_barricades,
                "required": total_barricades,
                "available": total_inventory_barricades,
            }
        )

    return {
        "station_usage": list(usage.values()),
        "constraints": constraints,
        "violations": violations,
    }


def escalation_rules(shortfall: int, violations: list[dict[str, Any]]) -> list[str]:
    rules = []
    if shortfall > 0:
        rules.append("Notify zone command and request reserve platoon coverage.")
    if any(item.get("type") == "shift_personnel_shortfall" for item in violations):
        rules.append("Rebalance nearest adjacent stations before approving plan.")
    if any(item.get("type") == "barricade_inventory_shortfall" for item in violations):
        rules.append("Escalate barricade inventory request to traffic control stores.")
    if not rules:
        rules.append("No escalation required under current constraints.")
    return rules


def build_scenario_plan(
    events: list[dict[str, Any]],
    profile: ScenarioProfile,
) -> dict[str, Any]:
    graph = get_graph()
    event_plans = []
    for event in events:
        forecast = predict_impact(event)
        context = scenario_event_features(event, forecast, profile)
        plan = generate_deployment_plan(
            context,
            graph=graph,
            control_radius_m=profile.control_radius_m,
            allocation_radius_m=profile.allocation_radius_m,
        )
        plan["event_id"] = event.get("id") or event.get("event_id")
        plan["event_name"] = event.get("name") or event.get("event_cause") or plan["event_id"]
        plan["scenario"] = profile.name
        plan["forecast"] = forecast
        add_travel_time_to_allocations(plan)
        event_plans.append(plan)

    constraints = constraint_summary(event_plans)
    shortfall = sum(int(plan.get("shortfall") or 0) for plan in event_plans)
    shortfall += sum(int(item.get("shortfall") or 0) for item in constraints["violations"])
    total_personnel = sum(int(plan.get("total_personnel") or 0) for plan in event_plans)
    total_barricades = sum(int(plan.get("total_barricades") or 0) for plan in event_plans)
    return {
        "scenario": profile.name,
        "operating_posture": profile.operating_posture,
        "event_count": len(events),
        "total_personnel": total_personnel,
        "total_barricades": total_barricades,
        "shortfall": shortfall,
        "constraint_violations": constraints["violations"],
        "station_usage": constraints["station_usage"],
        "escalations": escalation_rules(shortfall, constraints["violations"]),
        "event_plans": event_plans,
    }


def build_multi_incident_plan(
    events: list[dict[str, Any]],
    scenario_names: list[str] | None = None,
) -> dict[str, Any]:
    if not events:
        return {"event_count": 0, "scenarios": [], "recommended_scenario": None}

    selected = scenario_names or ["minimal", "recommended", "aggressive"]
    scenario_plans = [
        build_scenario_plan(events, SCENARIOS[name])
        for name in selected
        if name in SCENARIOS
    ]
    recommended = min(
        scenario_plans,
        key=lambda plan: (
            int(plan.get("shortfall") or 0),
            int(plan.get("total_personnel") or 0),
            str(plan.get("scenario")),
        ),
    )
    return {
        "event_count": len(events),
        "scenario_count": len(scenario_plans),
        "recommended_scenario": recommended["scenario"],
        "scenarios": scenario_plans,
    }
