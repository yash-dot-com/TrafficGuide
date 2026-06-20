from __future__ import annotations

import argparse
import json
import time

from backend.optimization.generate_plan import generate_deployment_plan
from backend.monitoring.operational_monitoring import operational_metrics_snapshot
from backend.geo.road_graph import graph_cache_metrics, reset_graph_cache_metrics


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark one deployment-plan run.")
    parser.add_argument("--lat", type=float, default=12.9819258)
    parser.add_argument("--lon", type=float, default=77.5945581)
    parser.add_argument("--corridor", default="CBD 2")
    parser.add_argument("--event-cause", default="water_logging")
    parser.add_argument("--repeat", type=int, default=2)
    return parser.parse_args()


def sample_event(args: argparse.Namespace) -> dict[str, object]:
    return {
        "id": "benchmark-event",
        "latitude": args.lat,
        "longitude": args.lon,
        "event_cause": args.event_cause,
        "event_type": "incident",
        "priority": "High",
        "corridor": args.corridor,
        "zone": "Central Zone 2",
        "police_station": "Cubbon Park",
        "start_datetime": "2026-06-19T09:30:00+05:30",
        "severity_label": "HIGH",
        "severity_probability": 0.72,
        "duration_low": 45,
        "duration_median": 120,
        "duration_high": 210,
        "risk_score": 0.72,
        "expected_delay_minutes": 90,
        "queue_length_m": 650,
        "requires_road_closure": False,
    }


def main() -> None:
    args = parse_args()
    reset_graph_cache_metrics()
    event = sample_event(args)
    runs = []
    plan = {}
    for _ in range(max(1, args.repeat)):
        started = time.perf_counter()
        plan = generate_deployment_plan(event)
        runs.append(time.perf_counter() - started)

    metrics = operational_metrics_snapshot(plan)
    result = {
        "runs": len(runs),
        "latency_seconds": {
            "first": round(runs[0], 3),
            "last": round(runs[-1], 3),
            "average": round(sum(runs) / len(runs), 3),
        },
        "plan": {
            "control_points": len(plan.get("control_points", [])),
            "personnel": plan.get("total_personnel"),
            "barricades": plan.get("total_barricades"),
            "diversions": len(plan.get("diversions", [])),
            "personnel_shortfall": plan.get("personnel_shortfall"),
            "barricade_shortfall": plan.get("barricade_shortfall"),
        },
        "route_quality": metrics["route_quality"],
        "resource_quality": metrics["resource_quality"],
        "graph_cache": graph_cache_metrics(),
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
