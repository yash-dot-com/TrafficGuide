from __future__ import annotations

import argparse
import json
import time
from typing import Any

from backend.optimization.allocation import allocate_barricades, allocate_personnel, load_police_stations
from backend.optimization.control_points import find_control_points
from backend.optimization.diversion import compute_diversions
from backend.geo.geo_utils import haversine_meters, nearest_node_by_haversine, node_lat_lon
from backend.optimization.resource_sizing import control_point_limit_for_event, size_event_resources
from backend.geo.road_graph import cache_demo_graph, get_graph, get_graph_for_point


def event_lat_lon(event_features: dict[str, Any]) -> tuple[float, float]:
    try:
        return float(event_features["latitude"]), float(event_features["longitude"])
    except KeyError as exc:
        raise ValueError("event_features must include latitude and longitude") from exc


def prediction_context(event_features: dict[str, Any]) -> dict[str, Any]:
    required_prediction_keys = {
        "severity_label",
        "severity_probability",
        "duration_low",
        "duration_median",
        "duration_high",
        "risk_score",
    }
    if required_prediction_keys.issubset(event_features):
        return dict(event_features)

    from backend.ml.predict import predict_impact

    predicted = predict_impact(event_features)
    merged = dict(event_features)
    merged.update(predicted)
    return merged


def generate_deployment_plan(
    event_features: dict[str, Any],
    graph: Any | None = None,
    control_radius_m: float | None = None,
    allocation_radius_m: float = 6_000.0,
) -> dict[str, Any]:
    start = time.perf_counter()
    event_lat, event_lon = event_lat_lon(event_features)
    context = prediction_context(event_features)

    road_graph = graph or get_graph_for_point(event_lat, event_lon)
    warnings: list[str] = []
    if road_graph.graph.get("cache_status") == "stale_fallback":
        warnings.append(str(road_graph.graph.get("cache_warning") or "Using stale road graph cache."))

    try:
        nearest_graph_node = nearest_node_by_haversine(road_graph, event_lat, event_lon)
        nearest_graph_distance_m = haversine_meters(
            event_lat,
            event_lon,
            *node_lat_lon(road_graph, nearest_graph_node),
        )
    except ValueError:
        nearest_graph_node = None
        nearest_graph_distance_m = None
        warnings.append("Road graph has no nodes available for this event.")

    search_radius = control_radius_m
    if search_radius is None:
        search_radius = 1200.0 if str(context.get("severity_label", "")).upper() == "HIGH" else 800.0

    control_points = find_control_points(
        event_lat,
        event_lon,
        search_radius_m=search_radius,
        graph=road_graph,
        limit=control_point_limit_for_event(context),
    )
    if not control_points:
        warnings.append("No usable control points were found near this event.")
    elif any(point.get("selection_method") == "nearest_graph_fallback" for point in control_points):
        warnings.append("Control points use nearest-graph fallback; refresh the road graph cache for this area.")

    resources = size_event_resources(control_points, context)
    stations = load_police_stations()
    allocation = allocate_personnel(
        resources["control_points"],
        stations=stations,
        max_radius_m=allocation_radius_m,
    )
    barricade_allocation = allocate_barricades(
        resources["control_points"],
        stations=stations,
        max_radius_m=allocation_radius_m,
    )
    diversions = compute_diversions(
        event_lat,
        event_lon,
        context,
        graph=road_graph,
    )
    if not diversions:
        warnings.append("No diversion route could be computed for the selected graph segment.")
    if barricade_allocation["shortfall"] > 0:
        warnings.append(
            f"Barricade shortfall: {barricade_allocation['shortfall']} units unavailable within allocation radius."
        )

    return {
        "event": {
            "latitude": event_lat,
            "longitude": event_lon,
            "severity_label": context.get("severity_label"),
            "severity_probability": context.get("severity_probability"),
            "duration_low": context.get("duration_low"),
            "duration_median": context.get("duration_median"),
            "duration_high": context.get("duration_high"),
            "risk_score": context.get("risk_score"),
        },
        "control_points": resources["control_points"],
        "total_personnel": resources["total_personnel"],
        "total_barricades": resources["total_barricades"],
        "allocations": allocation["allocations"],
        "barricade_allocations": barricade_allocation["allocations"],
        "personnel_shortfall": allocation["shortfall"],
        "barricade_shortfall": barricade_allocation["shortfall"],
        "shortfall": allocation["shortfall"],
        "allocation_solver": allocation["solver"],
        "barricade_allocation_solver": barricade_allocation["solver"],
        "diversions": diversions,
        "nearest_graph_node": int(nearest_graph_node) if nearest_graph_node is not None else None,
        "nearest_graph_distance_m": nearest_graph_distance_m,
        "graph_scope": road_graph.graph.get("route_graph_scope") or "city",
        "graph_cache_status": road_graph.graph.get("cache_status") or "unknown",
        "plan_warnings": warnings,
        "runtime_seconds": time.perf_counter() - start,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a sample deployment plan.")
    parser.add_argument("--lat", type=float, default=12.9716)
    parser.add_argument("--lon", type=float, default=77.5946)
    parser.add_argument("--demo-cache", action="store_true", help="Create/use a tiny offline graph cache")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    graph = None
    if args.demo_cache:
        graph = get_graph(cache_path=cache_demo_graph())

    sample = {
        "latitude": args.lat,
        "longitude": args.lon,
        "event_cause": "Accident",
        "corridor": "M G Road",
        "zone": "Central Zone 1",
        "police_station": "Cubbon Park",
        "veh_type": "Car",
        "start_datetime": "2026-06-18T09:30:00+05:30",
    }
    print(json.dumps(generate_deployment_plan(sample, graph=graph), indent=2))
