from __future__ import annotations

import math
from typing import Any


EARTH_RADIUS_M = 6_371_000.0


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def node_lat_lon(graph: Any, node_id: int) -> tuple[float, float]:
    node = graph.nodes[node_id]
    return float(node["y"]), float(node["x"])


def nearest_node_by_haversine(graph: Any, lat: float, lon: float) -> int:
    return min(
        graph.nodes,
        key=lambda node_id: haversine_meters(lat, lon, *node_lat_lon(graph, node_id)),
    )


def edge_highway_values(value: Any) -> set[str]:
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return {str(item).lower() for item in value}
    return {str(value).lower()}


def edge_names(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    name = str(value).strip()
    return [name] if name else []
