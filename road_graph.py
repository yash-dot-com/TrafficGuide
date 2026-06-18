from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any

import networkx as nx

from env_loader import load_project_env


load_project_env()


DEFAULT_BBOX = {
    "north": 13.08,
    "south": 12.86,
    "east": 77.78,
    "west": 77.45,
}
DEFAULT_CACHE_PATH = Path(__file__).with_name("graph_cache") / "bengaluru_drive_graph.pkl"
DEMO_CACHE_PATH = Path(__file__).with_name("graph_cache") / "bengaluru_demo_graph.pkl"
BBOX_TOLERANCE_DEGREES = 0.002


def parse_bbox(value: str | None = None) -> dict[str, float]:
    raw = value or os.environ.get("BENGALURU_BBOX")
    if not raw:
        return DEFAULT_BBOX.copy()

    parts = [part.strip() for part in raw.split(",")]
    if len(parts) != 4:
        raise ValueError(
            "BENGALURU_BBOX must be either 'south,west,north,east' "
            "or 'north,south,east,west'"
        )

    first, second, third, fourth = (float(part) for part in parts)

    # Prefer the common geospatial order used in the project .env:
    # south,west,north,east. Keep backward compatibility with the
    # earlier north,south,east,west convention used by the first script.
    if first < third and second < fourth:
        south, west, north, east = first, second, third, fourth
    else:
        north, south, east, west = first, second, third, fourth

    if not (south < north and west < east):
        raise ValueError(
            "Invalid BENGALURU_BBOX: expected south<north and west<east"
        )
    return {"north": north, "south": south, "east": east, "west": west}


def graph_cache_path(cache_path: str | Path | None = None) -> Path:
    path = Path(
        cache_path
        or os.environ.get("BENGALURU_GRAPH_CACHE")
        or DEFAULT_CACHE_PATH
    )
    if path.exists() and path.is_dir():
        return path / DEFAULT_CACHE_PATH.name
    if path.suffix:
        return path
    return path / DEFAULT_CACHE_PATH.name


def bbox_covers(
    cached_bbox: dict[str, float] | None,
    requested_bbox: dict[str, float],
    tolerance: float = BBOX_TOLERANCE_DEGREES,
) -> bool:
    if not cached_bbox:
        return False
    try:
        return (
            float(cached_bbox["north"]) + tolerance >= requested_bbox["north"]
            and float(cached_bbox["south"]) - tolerance <= requested_bbox["south"]
            and float(cached_bbox["east"]) + tolerance >= requested_bbox["east"]
            and float(cached_bbox["west"]) - tolerance <= requested_bbox["west"]
        )
    except (KeyError, TypeError, ValueError):
        return False


def refresh_stale_graph_enabled() -> bool:
    return os.environ.get("BENGALURU_REFRESH_STALE_GRAPH", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
    }


def mark_stale_graph(
    graph: nx.MultiDiGraph,
    requested_bbox: dict[str, float],
    message: str,
) -> nx.MultiDiGraph:
    graph.graph["cache_status"] = "stale_fallback"
    graph.graph["requested_bbox"] = requested_bbox
    graph.graph["cache_warning"] = message
    return graph


def _download_osm_graph(bbox: dict[str, float]) -> nx.MultiDiGraph:
    try:
        import osmnx as ox
    except ImportError as exc:
        raise RuntimeError(
            "osmnx is required to download the Bengaluru road graph. "
            "Install dependencies with: pip install -r requirements.txt"
        ) from exc

    ox.settings.use_cache = True
    ox.settings.log_console = False
    north = bbox["north"]
    south = bbox["south"]
    east = bbox["east"]
    west = bbox["west"]

    try:
        graph = ox.graph_from_bbox(
            (west, south, east, north),
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
        )
    except TypeError:
        graph = ox.graph_from_bbox(
            north,
            south,
            east,
            west,
            network_type="drive",
            simplify=True,
            retain_all=False,
            truncate_by_edge=True,
        )

    graph.graph["bbox"] = bbox
    graph.graph["source"] = "osmnx"
    return graph


def _save_graph(graph: nx.MultiDiGraph, cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("wb") as handle:
        pickle.dump(graph, handle, protocol=pickle.HIGHEST_PROTOCOL)


def _load_graph(cache_path: Path) -> nx.MultiDiGraph:
    with cache_path.open("rb") as handle:
        return pickle.load(handle)


def get_graph(
    bbox: dict[str, float] | None = None,
    cache_path: str | Path | None = None,
    force_download: bool = False,
) -> nx.MultiDiGraph:
    """Return a cached drivable Bengaluru OSM graph, downloading only on cache miss."""

    path = graph_cache_path(cache_path)
    requested_bbox = bbox or parse_bbox()
    stale_graph: nx.MultiDiGraph | None = None

    if path.exists():
        graph = _load_graph(path)
        source = graph.graph.get("source")
        cached_bbox = graph.graph.get("bbox")
        if not force_download and source != "offline_demo" and bbox_covers(cached_bbox, requested_bbox):
            graph.graph["cache_status"] = "fresh"
            return graph
        stale_graph = graph
        if not force_download and not refresh_stale_graph_enabled():
            return mark_stale_graph(
                stale_graph,
                requested_bbox,
                (
                    "Cached road graph does not cover the requested Bengaluru bbox. "
                    "Run get_graph(force_download=True) or set BENGALURU_REFRESH_STALE_GRAPH=true "
                    "to rebuild the cache."
                ),
            )

    try:
        graph = _download_osm_graph(requested_bbox)
    except Exception as exc:
        if stale_graph is None:
            raise
        return mark_stale_graph(
            stale_graph,
            requested_bbox,
            (
                "Cached road graph does not cover the requested Bengaluru bbox, "
                f"and refresh failed: {exc}"
            ),
        )

    graph.graph["cache_status"] = "fresh"
    _save_graph(graph, path)
    return graph


def cache_demo_graph(cache_path: str | Path | None = None) -> Path:
    """Create a tiny Bengaluru-shaped graph for offline tests when OSM is unavailable."""

    path = Path(cache_path) if cache_path else DEMO_CACHE_PATH
    if path.exists():
        return path

    center_lat = 12.9716
    center_lon = 77.5946
    step = 0.0045
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.graph["source"] = "offline_demo"

    node_id = 1
    grid: dict[tuple[int, int], int] = {}
    for row in range(-3, 4):
        for col in range(-3, 4):
            grid[(row, col)] = node_id
            graph.add_node(
                node_id,
                y=center_lat + row * step,
                x=center_lon + col * step,
            )
            node_id += 1

    for (row, col), source in grid.items():
        for d_row, d_col, name in [
            (0, 1, "M G Road"),
            (1, 0, "Outer Ring Road"),
        ]:
            target = grid.get((row + d_row, col + d_col))
            if target is None:
                continue
            highway = "primary" if row == 0 or col == 0 else "secondary"
            length = 500.0
            attrs = {"length": length, "highway": highway, "name": name}
            graph.add_edge(source, target, **attrs)
            graph.add_edge(target, source, **attrs)

    _save_graph(graph, path)
    return path
