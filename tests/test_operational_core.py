from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import networkx as nx
import pandas as pd

from backend.optimization.allocation import allocate_barricades
from backend.optimization.diversion import congestion_weight_function
from backend.optimization.resource_sizing import control_point_limit_for_event, size_control_point
from backend.geo.road_graph import cache_demo_graph, get_graph, graph_cache_metrics, reset_graph_cache_metrics


class OperationalCoreTests(unittest.TestCase):
    def test_graph_cache_uses_memory_after_first_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "demo_graph.pkl"
            cache_demo_graph(cache_path)
            reset_graph_cache_metrics()

            first = get_graph(cache_path=cache_path)
            second = get_graph(cache_path=cache_path)
            metrics = graph_cache_metrics()

            self.assertIs(first, second)
            self.assertGreaterEqual(metrics["requests"], 2)
            self.assertGreaterEqual(metrics["memory_hits"], 1)
            self.assertGreaterEqual(metrics["cache_hit_rate"], 1.0)

    def test_congestion_weight_prefers_lower_risk_route(self) -> None:
        graph = nx.MultiDiGraph()
        graph.add_node(1, y=0.0, x=0.0)
        graph.add_node(2, y=0.0, x=0.01)
        graph.add_node(3, y=0.01, x=0.0)
        graph.add_node(4, y=0.01, x=0.01)
        graph.add_edge(1, 2, length=100.0, name="Risk Road")
        graph.add_edge(2, 4, length=100.0, name="Risk Road")
        graph.add_edge(1, 3, length=130.0, name="Safe Road")
        graph.add_edge(3, 4, length=130.0, name="Safe Road")
        risk_density = pd.DataFrame(
            [
                {"corridor": "Risk Road", "hour_bucket": 9, "day_of_week": 0, "risk_score": 1.0},
                {"corridor": "Safe Road", "hour_bucket": 9, "day_of_week": 0, "risk_score": 0.0},
            ]
        )
        event = {"start_datetime": "2026-06-22T09:30:00+05:30", "corridor": "Risk Road"}
        route = nx.shortest_path(
            graph,
            1,
            4,
            weight=congestion_weight_function(graph, risk_density, event),
        )
        self.assertEqual(route, [1, 3, 4])

    def test_resource_sizing_adds_barricade_strategy(self) -> None:
        point = {"node_id": 10, "lane_estimate": 4, "is_arterial": True}
        event = {
            "event_cause": "rally",
            "priority": "High",
            "severity_label": "HIGH",
            "severity_probability": 0.78,
            "risk_score": 0.72,
            "expected_delay_minutes": 140,
            "queue_length_m": 700,
            "duration_median": 90,
            "requires_road_closure": False,
        }
        sized = size_control_point(point, event)
        self.assertGreaterEqual(sized["personnel_needed"], 5)
        self.assertGreaterEqual(sized["barricades_needed"], 3)
        self.assertEqual(
            sized["barricade_strategy"]["placement"],
            "crowd_route_filter_points_with_pedestrian_buffer",
        )

    def test_pothole_sizing_is_localized(self) -> None:
        point = {"node_id": 11, "lane_estimate": 4, "is_arterial": True}
        event = {
            "event_cause": "pot_holes",
            "priority": "High",
            "severity_label": "LOW",
            "severity_probability": 0.24,
            "risk_score": 0.66,
            "expected_delay_minutes": 50,
            "queue_length_m": 140,
            "duration_median": 40,
            "requires_road_closure": False,
        }
        sized = size_control_point(point, event)
        self.assertEqual(control_point_limit_for_event(event), 2)
        self.assertLessEqual(sized["personnel_needed"], 3)
        self.assertLessEqual(sized["barricades_needed"], 3)
        self.assertEqual(
            sized["barricade_strategy"]["placement"],
            "localized_hazard_taper_with_warning_cones",
        )

    def test_waterlogging_sizing_is_heavier_than_pothole(self) -> None:
        point = {"node_id": 12, "lane_estimate": 4, "is_arterial": True}
        event = {
            "event_cause": "water_logging",
            "priority": "High",
            "severity_label": "HIGH",
            "severity_probability": 0.78,
            "risk_score": 0.72,
            "expected_delay_minutes": 140,
            "queue_length_m": 700,
            "duration_median": 120,
            "requires_road_closure": False,
        }
        sized = size_control_point(point, event)
        self.assertEqual(control_point_limit_for_event(event), 5)
        self.assertGreaterEqual(sized["personnel_needed"], 5)
        self.assertGreaterEqual(sized["barricades_needed"], 3)
        self.assertEqual(
            sized["barricade_strategy"]["placement"],
            "flooded_lane_filter_with_depth_warning",
        )

    def test_barricade_allocation_reports_inventory_shortfall(self) -> None:
        points = [
            {"node_id": 1, "lat": 12.97, "lon": 77.59, "barricades_needed": 6},
            {"node_id": 2, "lat": 12.971, "lon": 77.591, "barricades_needed": 6},
        ]
        stations = [
            {
                "id": 1,
                "name": "Test Station",
                "latitude": 12.97,
                "longitude": 77.59,
                "available_personnel": 10,
                "available_barricades": 8,
            }
        ]
        allocation = allocate_barricades(points, stations=stations, max_radius_m=1_000)
        self.assertEqual(allocation["shortfall"], 4)
        self.assertEqual(sum(row["barricades_assigned"] for row in allocation["allocations"]), 8)


if __name__ == "__main__":
    unittest.main()
