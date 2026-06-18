from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import networkx as nx
import pandas as pd

from geo_utils import edge_names, haversine_meters, nearest_node_by_haversine, node_lat_lon
from road_graph import get_graph


MODEL_DIR = Path(__file__).with_name("models")
HOUR_BUCKET_SIZE = 3


def hour_bucket(hour_of_day: int) -> int:
    if hour_of_day < 0:
        return -1
    return int(hour_of_day // HOUR_BUCKET_SIZE * HOUR_BUCKET_SIZE)


def event_time_parts(event_features: dict[str, Any]) -> tuple[int, int]:
    timestamp = pd.to_datetime(event_features.get("start_datetime"), errors="coerce", utc=True)
    if pd.isna(timestamp):
        return -1, -1
    return int(timestamp.hour), int(timestamp.dayofweek)


def load_risk_density() -> pd.DataFrame:
    path = MODEL_DIR / "risk_density.parquet"
    if not path.exists():
        return pd.DataFrame(columns=["corridor", "hour_bucket", "day_of_week", "risk_score"])
    return pd.read_parquet(path)


def risk_for_corridor(
    risk_density: pd.DataFrame,
    corridor: str,
    bucket: int,
    day_of_week: int,
) -> float:
    if risk_density.empty or not corridor:
        return 0.0
    exact = risk_density.loc[
        (risk_density["corridor"].astype(str) == str(corridor))
        & (risk_density["hour_bucket"] == bucket)
        & (risk_density["day_of_week"] == day_of_week)
    ]
    if not exact.empty:
        return float(exact["risk_score"].iloc[0])
    corridor_rows = risk_density.loc[risk_density["corridor"].astype(str) == str(corridor)]
    if corridor_rows.empty:
        return 0.0
    return float(corridor_rows["risk_score"].mean())


def incident_corridors(graph: nx.MultiDiGraph, node_id: int) -> set[str]:
    names: set[str] = set()
    edge_iterators = [graph.out_edges(node_id, data=True)]
    if graph.is_directed():
        edge_iterators.append(graph.in_edges(node_id, data=True))

    for iterator in edge_iterators:
        for _, _, data in iterator:
            names.update(edge_names(data.get("name")))
            names.update(edge_names(data.get("ref")))
    return names


def route_has_high_risk_node(
    graph: nx.MultiDiGraph,
    route: list[int],
    risk_density: pd.DataFrame,
    event_features: dict[str, Any],
    threshold: float = 0.8,
) -> bool:
    hour_of_day, day_of_week = event_time_parts(event_features)
    bucket = hour_bucket(hour_of_day)
    for node_id in route:
        for corridor in incident_corridors(graph, node_id):
            if risk_for_corridor(risk_density, corridor, bucket, day_of_week) > threshold:
                return True
    return False


def path_length_m(graph: nx.MultiDiGraph, route: list[int]) -> float:
    length = 0.0
    for source, target in zip(route, route[1:]):
        edge_data = graph.get_edge_data(source, target, default={})
        if not edge_data:
            length += haversine_meters(*node_lat_lon(graph, source), *node_lat_lon(graph, target))
            continue
        length += min(float(data.get("length") or 0.0) for data in edge_data.values())
    return length


def remove_event_edges(
    graph: nx.MultiDiGraph,
    event_node: int,
    event_lat: float,
    event_lon: float,
    block_radius_m: float = 120.0,
) -> nx.MultiDiGraph:
    modified = graph.copy()
    nearby_nodes = [
        node_id
        for node_id in graph.nodes
        if haversine_meters(event_lat, event_lon, *node_lat_lon(graph, node_id)) <= block_radius_m
    ]
    if event_node not in nearby_nodes:
        nearby_nodes.append(event_node)

    edges_to_remove: set[tuple[int, int, int]] = set()
    for node_id in nearby_nodes:
        for source, target, key in graph.out_edges(node_id, keys=True):
            edges_to_remove.add((source, target, key))
        if graph.is_directed():
            for source, target, key in graph.in_edges(node_id, keys=True):
                edges_to_remove.add((source, target, key))

    modified.remove_edges_from(edges_to_remove)
    return modified


def angle_from_event(graph: nx.MultiDiGraph, node_id: int, event_lat: float, event_lon: float) -> float:
    node_lat, node_lon = node_lat_lon(graph, node_id)
    return math.atan2(node_lat - event_lat, node_lon - event_lon)


def endpoint_pairs(
    graph: nx.MultiDiGraph,
    event_node: int,
    event_lat: float,
    event_lon: float,
    target_distance_m: float = 1500.0,
) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []

    def add_pair(source: int, target: int) -> None:
        if source == target:
            return
        pair = (source, target)
        reverse_pair = (target, source)
        if pair not in pairs and reverse_pair not in pairs:
            pairs.append(pair)

    neighbor_nodes: set[int] = set()
    for _, target in graph.out_edges(event_node):
        neighbor_nodes.add(target)
    if graph.is_directed():
        for source, _ in graph.in_edges(event_node):
            neighbor_nodes.add(source)

    ordered_neighbors = sorted(
        neighbor_nodes,
        key=lambda node_id: haversine_meters(
            *node_lat_lon(graph, event_node),
            *node_lat_lon(graph, node_id),
        ),
    )[:16]
    for index, source in enumerate(ordered_neighbors):
        source_angle = angle_from_event(graph, source, event_lat, event_lon)
        for target in ordered_neighbors[index + 1:]:
            angle_delta = abs(math.atan2(
                math.sin(source_angle - angle_from_event(graph, target, event_lat, event_lon)),
                math.cos(source_angle - angle_from_event(graph, target, event_lat, event_lon)),
            ))
            if angle_delta >= math.radians(90):
                add_pair(source, target)
            if len(pairs) >= 8:
                return pairs

    search_graph = graph.to_undirected(as_view=True)
    lengths = nx.single_source_dijkstra_path_length(
        search_graph,
        event_node,
        cutoff=target_distance_m * 1.45,
        weight="length",
    )
    candidates = [
        node_id
        for node_id, distance in lengths.items()
        if target_distance_m * 0.65 <= distance <= target_distance_m * 1.45
    ]
    candidates.sort(
        key=lambda node_id: abs(lengths[node_id] - target_distance_m)
    )
    candidates = candidates[:16]

    for index, source in enumerate(candidates):
        source_angle = angle_from_event(graph, source, event_lat, event_lon)
        for target in candidates[index + 1:]:
            angle_delta = abs(math.atan2(
                math.sin(source_angle - angle_from_event(graph, target, event_lat, event_lon)),
                math.cos(source_angle - angle_from_event(graph, target, event_lat, event_lon)),
            ))
            if angle_delta < math.radians(120):
                continue
            add_pair(source, target)
            if len(pairs) >= 8:
                return pairs
    return pairs


def route_coordinates(graph: nx.MultiDiGraph, route: list[int]) -> list[dict[str, float]]:
    return [
        {"lat": node_lat_lon(graph, node_id)[0], "lon": node_lat_lon(graph, node_id)[1]}
        for node_id in route
    ]


def compute_diversions(
    event_lat: float,
    event_lon: float,
    event_features: dict[str, Any],
    graph: nx.MultiDiGraph | None = None,
    limit: int = 3,
) -> list[dict[str, Any]]:
    road_graph = graph or get_graph()
    event_node = nearest_node_by_haversine(road_graph, event_lat, event_lon)
    risk_density = load_risk_density()
    pairs = endpoint_pairs(road_graph, event_node, event_lat, event_lon)

    diversions: list[dict[str, Any]] = []
    seen_paths: set[tuple[int, ...]] = set()
    for block_radius_m in (120.0, 240.0, 400.0):
        modified_graph = remove_event_edges(
            road_graph,
            event_node,
            event_lat,
            event_lon,
            block_radius_m=block_radius_m,
        )
        for source, target in pairs:
            route_pair: tuple[list[int], list[int], int, int] | None = None
            for candidate_source, candidate_target in ((source, target), (target, source)):
                try:
                    original_route = nx.shortest_path(
                        road_graph,
                        candidate_source,
                        candidate_target,
                        weight="length",
                    )
                    alternate_route = nx.shortest_path(
                        modified_graph,
                        candidate_source,
                        candidate_target,
                        weight="length",
                    )
                except (nx.NetworkXNoPath, nx.NodeNotFound):
                    continue
                route_pair = (
                    original_route,
                    alternate_route,
                    candidate_source,
                    candidate_target,
                )
                break
            if route_pair is None:
                continue

            original_route, alternate_route, actual_source, actual_target = route_pair

            if alternate_route == original_route:
                continue
            if event_node in alternate_route:
                continue
            path_key = tuple(int(node_id) for node_id in alternate_route)
            if path_key in seen_paths:
                continue
            if route_has_high_risk_node(road_graph, alternate_route, risk_density, event_features):
                continue

            seen_paths.add(path_key)
            original_length = path_length_m(road_graph, original_route)
            alternate_length = path_length_m(road_graph, alternate_route)
            diversions.append(
                {
                    "source_node_id": int(actual_source),
                    "target_node_id": int(actual_target),
                    "original_length_m": original_length,
                    "diversion_length_m": alternate_length,
                    "added_length_m": max(0.0, alternate_length - original_length),
                    "block_radius_m": block_radius_m,
                    "path_node_ids": [int(node_id) for node_id in alternate_route],
                    "path": route_coordinates(road_graph, alternate_route),
                }
            )

            if len(diversions) >= limit:
                break
        if len(diversions) >= limit:
            break

    diversions.sort(key=lambda item: (item["added_length_m"], item["diversion_length_m"]))
    for rank, diversion in enumerate(diversions[:limit], start=1):
        diversion["rank"] = rank
    return diversions[:limit]
