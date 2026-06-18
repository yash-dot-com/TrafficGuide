from __future__ import annotations

from typing import Any

import networkx as nx

from geo_utils import edge_highway_values, haversine_meters, node_lat_lon
from road_graph import get_graph


ARTERIAL_HIGHWAYS = {
    "motorway",
    "trunk",
    "primary",
    "secondary",
    "motorway_link",
    "trunk_link",
    "primary_link",
    "secondary_link",
}


def incident_edge_data(graph: nx.MultiDiGraph, node_id: int) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    if graph.is_directed():
        edges.extend(data for _, _, data in graph.out_edges(node_id, data=True))
        edges.extend(data for _, _, data in graph.in_edges(node_id, data=True))
    else:
        edges.extend(data for _, _, data in graph.edges(node_id, data=True))
    return edges


def is_arterial_node(graph: nx.MultiDiGraph, node_id: int) -> bool:
    for data in incident_edge_data(graph, node_id):
        if edge_highway_values(data.get("highway")) & ARTERIAL_HIGHWAYS:
            return True
    return False


def find_control_points(
    event_lat: float,
    event_lon: float,
    search_radius_m: float = 800.0,
    graph: nx.MultiDiGraph | None = None,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Find nearby junction nodes, capped at the most connected candidates.

    The first pass honors the requested radius and only picks true junctions.
    Later passes deliberately relax the radius/degree filters so stale or sparse
    graph coverage does not collapse the whole deployment plan to zero.
    """

    road_graph = graph or get_graph()
    nodes: list[dict[str, Any]] = []
    for node_id in road_graph.nodes:
        node_lat, node_lon = node_lat_lon(road_graph, node_id)
        distance_m = haversine_meters(event_lat, event_lon, node_lat, node_lon)
        edge_count = int(road_graph.degree(node_id))
        nodes.append(
            {
                "node_id": int(node_id),
                "lat": node_lat,
                "lon": node_lon,
                "distance_m": distance_m,
                "lane_estimate": max(1, edge_count),
                "is_arterial": is_arterial_node(road_graph, node_id),
                "_edge_count": edge_count,
            }
        )

    def ranked_candidates(
        radius_m: float | None,
        min_degree: int,
        selection_method: str,
    ) -> list[dict[str, Any]]:
        selected = [
            dict(node, selection_method=selection_method, search_radius_m=search_radius_m)
            for node in nodes
            if node["_edge_count"] >= min_degree
            and (radius_m is None or float(node["distance_m"]) <= radius_m)
        ]
        selected.sort(
            key=lambda item: (
                -int(item["lane_estimate"]),
                float(item["distance_m"]),
                int(item["node_id"]),
            )
        )
        for item in selected:
            item.pop("_edge_count", None)
        return selected[:limit]

    search_tiers = [
        (search_radius_m, 3, "junction_within_radius"),
        (max(search_radius_m * 1.75, 1_600.0), 3, "junction_expanded_radius"),
        (max(search_radius_m * 3.0, 3_000.0), 3, "junction_wide_radius"),
        (max(search_radius_m * 6.0, 6_000.0), 2, "traffic_node_wide_radius"),
        (None, 2, "nearest_graph_fallback"),
        (None, 1, "nearest_graph_fallback"),
    ]
    for radius_m, min_degree, selection_method in search_tiers:
        candidates = ranked_candidates(radius_m, min_degree, selection_method)
        if candidates:
            return candidates

    return []
