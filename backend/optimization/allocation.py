from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from backend.config.env_loader import load_project_env
from backend.geo.geo_utils import haversine_meters


load_project_env()

DEFAULT_MAX_RADIUS_M = 6_000.0
NEAREST_STATIONS_PER_POINT = 5
DEFAULT_SHIFT_AVAILABILITY_FACTOR = 0.82

FALLBACK_STATIONS = [
    {"id": 1, "name": "Yelahanka", "zone": "North Zone 2", "latitude": 13.101419, "longitude": 77.596026, "available_personnel": 31, "available_barricades": 48},
    {"id": 2, "name": "HAL Old Airport", "zone": "East Zone 1", "latitude": 12.953229, "longitude": 77.697134, "available_personnel": 24, "available_barricades": 35},
    {"id": 3, "name": "Sadashivanagar", "zone": "Central Zone 1", "latitude": 13.010332, "longitude": 77.579722, "available_personnel": 19, "available_barricades": 27},
    {"id": 4, "name": "Byatarayanapura", "zone": "West Zone 2", "latitude": 12.949359, "longitude": 77.534226, "available_personnel": 22, "available_barricades": 31},
    {"id": 5, "name": "Halasuru Gate", "zone": "Central Zone 2", "latitude": 12.967149, "longitude": 77.587305, "available_personnel": 28, "available_barricades": 41},
    {"id": 6, "name": "Yeshwanthpura", "zone": "North Zone 1", "latitude": 13.026197, "longitude": 77.544762, "available_personnel": 26, "available_barricades": 44},
    {"id": 7, "name": "Hennuru", "zone": "East Zone 2", "latitude": 13.044663, "longitude": 77.633338, "available_personnel": 20, "available_barricades": 29},
    {"id": 8, "name": "Kodigehalli", "zone": "North Zone 2", "latitude": 13.047052, "longitude": 77.585742, "available_personnel": 18, "available_barricades": 24},
    {"id": 9, "name": "Banaswadi", "zone": "East Zone 1", "latitude": 13.000874, "longitude": 77.656685, "available_personnel": 27, "available_barricades": 39},
    {"id": 10, "name": "K.R. Pura", "zone": "East Zone 2", "latitude": 13.016153, "longitude": 77.705730, "available_personnel": 32, "available_barricades": 46},
    {"id": 11, "name": "Kamakshipalya", "zone": "West Zone 1", "latitude": 12.987790, "longitude": 77.507889, "available_personnel": 23, "available_barricades": 33},
    {"id": 12, "name": "Cubbon Park", "zone": "Central Zone 1", "latitude": 12.978084, "longitude": 77.595608, "available_personnel": 21, "available_barricades": 30},
    {"id": 13, "name": "Jalahalli", "zone": "North Zone 1", "latitude": 13.043600, "longitude": 77.548758, "available_personnel": 17, "available_barricades": 25},
    {"id": 14, "name": "Chamarajpet", "zone": "Central Zone 2", "latitude": 12.965532, "longitude": 77.563788, "available_personnel": 20, "available_barricades": 28},
    {"id": 15, "name": "High ground", "zone": "Central Zone 1", "latitude": 12.988736, "longitude": 77.585475, "available_personnel": 18, "available_barricades": 26},
]


def load_police_stations() -> list[dict[str, Any]]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        return [dict(station) for station in FALLBACK_STATIONS]

    import pandas as pd
    from sqlalchemy import create_engine, text

    engine = create_engine(database_url, future=True)
    query = text(
        """
        SELECT
            id,
            name,
            zone,
            latitude,
            longitude,
            available_personnel,
            available_barricades
        FROM police_stations
        WHERE latitude IS NOT NULL
            AND longitude IS NOT NULL
            AND available_personnel > 0
        """
    )
    frame = pd.read_sql_query(query, engine)
    return frame.to_dict(orient="records")


def effective_personnel(station: dict[str, Any]) -> int:
    if station.get("shift_available_personnel") is not None:
        return max(0, int(station.get("shift_available_personnel") or 0))
    return max(0, int(int(station.get("available_personnel") or 0) * DEFAULT_SHIFT_AVAILABILITY_FACTOR))


def effective_barricades(station: dict[str, Any]) -> int:
    return max(0, int(station.get("available_barricades") or 0))


def candidate_station_pairs(
    control_points: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    max_radius_m: float,
) -> dict[tuple[int, int], float]:
    distances: dict[tuple[int, int], float] = {}
    for point_index, point in enumerate(control_points):
        ranked: list[tuple[int, float]] = []
        for station_index, station in enumerate(stations):
            distance_m = haversine_meters(
                float(point["lat"]),
                float(point["lon"]),
                float(station["latitude"]),
                float(station["longitude"]),
            )
            if distance_m <= max_radius_m:
                ranked.append((station_index, distance_m))

        ranked.sort(key=lambda item: item[1])
        for station_index, distance_m in ranked[:NEAREST_STATIONS_PER_POINT]:
            distances[(station_index, point_index)] = distance_m
    return distances


def _greedy_allocate(
    control_points: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    distances: dict[tuple[int, int], float],
) -> dict[str, Any]:
    remaining = {
        station_index: effective_personnel(station)
        for station_index, station in enumerate(stations)
    }
    allocations: list[dict[str, Any]] = []
    shortfall = 0

    for point_index, point in enumerate(control_points):
        needed = int(point.get("personnel_needed") or 0)
        for (station_index, candidate_point_index), distance_m in sorted(
            distances.items(), key=lambda item: item[1]
        ):
            if candidate_point_index != point_index or needed <= 0:
                continue
            assigned = min(needed, remaining[station_index])
            if assigned <= 0:
                continue
            remaining[station_index] -= assigned
            needed -= assigned
            allocations.append(
                {
                    "control_point_node_id": point["node_id"],
                    "station_id": stations[station_index]["id"],
                    "station_name": stations[station_index]["name"],
                    "personnel_assigned": assigned,
                    "distance_m": distance_m,
                }
            )
        shortfall += needed

    return {
        "allocations": allocations,
        "shortfall": shortfall,
        "solver": "greedy_fallback",
    }


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except (AttributeError, ValueError):
            return value
    return value


def _allocate_with_child_process(
    control_points: list[dict[str, Any]],
    stations: list[dict[str, Any]],
    max_radius_m: float,
) -> dict[str, Any] | None:
    payload = {
        "control_points": _jsonable(control_points),
        "stations": _jsonable(stations),
        "max_radius_m": max_radius_m,
    }
    command = [sys.executable, str(Path(__file__).resolve()), "--solve-json"]
    try:
        completed = subprocess.run(
            command,
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return json.loads(completed.stdout)


def allocate_personnel(
    control_points: list[dict[str, Any]],
    stations: list[dict[str, Any]] | None = None,
    max_radius_m: float = DEFAULT_MAX_RADIUS_M,
    use_subprocess: bool = True,
) -> dict[str, Any]:
    stations = stations or load_police_stations()
    total_required = sum(int(point.get("personnel_needed") or 0) for point in control_points)
    if total_required <= 0:
        return {"allocations": [], "shortfall": 0, "solver": "none"}

    distances = candidate_station_pairs(control_points, stations, max_radius_m)
    if not distances:
        return {"allocations": [], "shortfall": total_required, "solver": "none"}

    if use_subprocess:
        child_result = _allocate_with_child_process(control_points, stations, max_radius_m)
        if child_result is not None:
            return child_result
        return _greedy_allocate(control_points, stations, distances)

    try:
        from ortools.linear_solver import pywraplp
    except ImportError:
        return _greedy_allocate(control_points, stations, distances)

    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        return _greedy_allocate(control_points, stations, distances)

    assignment_vars: dict[tuple[int, int], Any] = {}
    for station_index, point_index in distances:
        assignment_vars[(station_index, point_index)] = solver.IntVar(
            0,
            solver.infinity(),
            f"x_s{station_index}_p{point_index}",
        )

    shortfall_vars: dict[int, Any] = {}
    for point_index, point in enumerate(control_points):
        needed = int(point.get("personnel_needed") or 0)
        shortfall_vars[point_index] = solver.IntVar(0, needed, f"shortfall_p{point_index}")
        solver.Add(
            sum(
                assignment_vars[(station_index, point_index)]
                for station_index in range(len(stations))
                if (station_index, point_index) in assignment_vars
            )
            + shortfall_vars[point_index]
            == needed
        )

    for station_index, station in enumerate(stations):
        solver.Add(
            sum(
                assignment_vars[(station_index, point_index)]
                for point_index in range(len(control_points))
                if (station_index, point_index) in assignment_vars
            )
            <= effective_personnel(station)
        )

    objective = solver.Objective()
    shortfall_penalty = max(max(distances.values()), 1.0) * 1000.0
    for key, variable in assignment_vars.items():
        objective.SetCoefficient(variable, distances[key])
    for variable in shortfall_vars.values():
        objective.SetCoefficient(variable, shortfall_penalty)
    objective.SetMinimization()

    status = solver.Solve()
    if status not in {pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE}:
        return _greedy_allocate(control_points, stations, distances)

    allocations: list[dict[str, Any]] = []
    for (station_index, point_index), variable in assignment_vars.items():
        assigned = int(round(variable.solution_value()))
        if assigned <= 0:
            continue
        allocations.append(
            {
                "control_point_node_id": control_points[point_index]["node_id"],
                "station_id": stations[station_index]["id"],
                "station_name": stations[station_index]["name"],
                "personnel_assigned": assigned,
                "distance_m": distances[(station_index, point_index)],
            }
        )

    allocations.sort(key=lambda item: (item["control_point_node_id"], item["distance_m"]))
    shortfall = sum(int(round(variable.solution_value())) for variable in shortfall_vars.values())
    return {
        "allocations": allocations,
        "shortfall": shortfall,
        "solver": "ortools_cbc",
    }


def allocate_barricades(
    control_points: list[dict[str, Any]],
    stations: list[dict[str, Any]] | None = None,
    max_radius_m: float = DEFAULT_MAX_RADIUS_M,
) -> dict[str, Any]:
    stations = stations or load_police_stations()
    total_required = sum(int(point.get("barricades_needed") or 0) for point in control_points)
    if total_required <= 0:
        return {"allocations": [], "shortfall": 0, "solver": "none"}

    distances = candidate_station_pairs(control_points, stations, max_radius_m)
    if not distances:
        return {"allocations": [], "shortfall": total_required, "solver": "none"}

    remaining = {
        station_index: effective_barricades(station)
        for station_index, station in enumerate(stations)
    }
    allocations: list[dict[str, Any]] = []
    shortfall = 0

    for point_index, point in enumerate(control_points):
        needed = int(point.get("barricades_needed") or 0)
        for (station_index, candidate_point_index), distance_m in sorted(
            distances.items(),
            key=lambda item: item[1],
        ):
            if candidate_point_index != point_index or needed <= 0:
                continue
            assigned = min(needed, remaining[station_index])
            if assigned <= 0:
                continue
            remaining[station_index] -= assigned
            needed -= assigned
            allocations.append(
                {
                    "control_point_node_id": point["node_id"],
                    "station_id": stations[station_index]["id"],
                    "station_name": stations[station_index]["name"],
                    "barricades_assigned": assigned,
                    "distance_m": distance_m,
                }
            )
        shortfall += needed

    return {
        "allocations": allocations,
        "shortfall": shortfall,
        "solver": "greedy_inventory",
    }


def _main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] != "--solve-json":
        raise SystemExit("Usage: python allocation.py --solve-json < payload.json")

    payload = json.loads(sys.stdin.read())
    result = allocate_personnel(
        payload["control_points"],
        stations=payload["stations"],
        max_radius_m=float(payload["max_radius_m"]),
        use_subprocess=False,
    )
    print(json.dumps(result))


if __name__ == "__main__":
    _main()
