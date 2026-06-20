from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


APP_ROOT = Path(__file__).resolve().parent
INTEGRATION_DIR = APP_ROOT / "integrations"
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class FeedStatus:
    name: str
    category: str
    mode: str
    records: int
    last_seen: str
    freshness_seconds: int
    health: str = "ok"

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "mode": self.mode,
            "records": self.records,
            "last_seen": self.last_seen,
            "freshness_seconds": self.freshness_seconds,
            "health": self.health,
        }


def now_ist() -> datetime:
    return datetime.now(LOCAL_TZ)


def iso_at(minutes_delta: int) -> str:
    return (now_ist() + timedelta(minutes=minutes_delta)).isoformat()


def read_json_feed(file_name: str) -> list[dict[str, Any]] | None:
    path = INTEGRATION_DIR / file_name
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        return payload["records"]
    return None


def live_incidents() -> list[dict[str, Any]]:
    configured = read_json_feed("live_incidents.json")
    if configured is not None:
        return configured

    return [
        {
            "id": "astra-live-silk-board-01",
            "source": "astra_live_incident_feed",
            "event_type": "incident",
            "name": "Crash near Silk Board flyover",
            "latitude": 12.91786,
            "longitude": 77.62391,
            "event_cause": "accident",
            "priority": "High",
            "status": "active",
            "corridor": "Outer Ring Road",
            "zone": "South East Zone",
            "police_station": "Madiwala",
            "start_datetime": iso_at(-18),
            "requires_road_closure": True,
            "feed_confidence": 0.92,
        },
        {
            "id": "astra-live-mg-road-02",
            "source": "astra_live_incident_feed",
            "event_type": "incident",
            "name": "Waterlogging near Trinity circle",
            "latitude": 12.97382,
            "longitude": 77.61718,
            "event_cause": "waterlogging",
            "priority": "High",
            "status": "active",
            "corridor": "M G Road",
            "zone": "Central Zone 1",
            "police_station": "Cubbon Park",
            "start_datetime": iso_at(-34),
            "requires_road_closure": False,
            "feed_confidence": 0.87,
        },
        {
            "id": "astra-live-hebbal-03",
            "source": "astra_live_incident_feed",
            "event_type": "incident",
            "name": "Slow traffic at Hebbal loop",
            "latitude": 13.03568,
            "longitude": 77.58963,
            "event_cause": "breakdown",
            "priority": "Low",
            "status": "active",
            "corridor": "Bellary Road",
            "zone": "North Zone 1",
            "police_station": "Hebbal",
            "start_datetime": iso_at(-11),
            "requires_road_closure": False,
            "feed_confidence": 0.78,
        },
    ]


def planned_permits() -> list[dict[str, Any]]:
    configured = read_json_feed("planned_permits.json")
    if configured is not None:
        return configured

    return [
        {
            "id": "permit-kanteerava-sports-01",
            "source": "planned_permit_feed",
            "event_type": "planned",
            "name": "Evening football crowd, Kanteerava",
            "latitude": 12.96978,
            "longitude": 77.59373,
            "event_cause": "public_event",
            "priority": "High",
            "status": "planned",
            "corridor": "Kasturba Road",
            "zone": "Central Zone 1",
            "police_station": "Cubbon Park",
            "scheduled_start": iso_at(210),
            "requires_road_closure": False,
        },
        {
            "id": "permit-whitefield-metro-work-02",
            "source": "planned_permit_feed",
            "event_type": "planned",
            "name": "Night utility work, Whitefield corridor",
            "latitude": 12.96995,
            "longitude": 77.74997,
            "event_cause": "construction",
            "priority": "Low",
            "status": "planned",
            "corridor": "Whitefield Main Road",
            "zone": "East Zone 2",
            "police_station": "K.R. Pura",
            "scheduled_start": iso_at(390),
            "requires_road_closure": True,
        },
    ]


def gps_speed_feed() -> list[dict[str, Any]]:
    configured = read_json_feed("gps_speeds.json")
    if configured is not None:
        return configured

    return [
        {"corridor": "Outer Ring Road", "current_speed_kmph": 13.8, "free_flow_speed_kmph": 38.0, "sample_size": 428},
        {"corridor": "M G Road", "current_speed_kmph": 11.9, "free_flow_speed_kmph": 31.0, "sample_size": 214},
        {"corridor": "Bellary Road", "current_speed_kmph": 24.2, "free_flow_speed_kmph": 44.0, "sample_size": 173},
        {"corridor": "Kasturba Road", "current_speed_kmph": 16.4, "free_flow_speed_kmph": 29.0, "sample_size": 96},
        {"corridor": "Whitefield Main Road", "current_speed_kmph": 18.5, "free_flow_speed_kmph": 36.0, "sample_size": 188},
    ]


def weather_feed() -> dict[str, Any]:
    configured = read_json_feed("weather.json")
    if configured:
        return configured[0]

    return {
        "source": "weather_rain_flood_feed",
        "rainfall_mm_1h": 12.4,
        "rainfall_intensity": "moderate",
        "flood_risk": 0.42,
        "road_surface": "wet",
        "observed_at": now_ist().isoformat(),
    }


def sensor_counts() -> list[dict[str, Any]]:
    configured = read_json_feed("sensor_counts.json")
    if configured is not None:
        return configured

    return [
        {"sensor_id": "cctv-silk-board-north", "corridor": "Outer Ring Road", "vehicle_count_15m": 1382, "heavy_vehicle_share": 0.14},
        {"sensor_id": "anpr-mg-road-east", "corridor": "M G Road", "vehicle_count_15m": 754, "heavy_vehicle_share": 0.05},
        {"sensor_id": "cctv-hebbal-loop", "corridor": "Bellary Road", "vehicle_count_15m": 901, "heavy_vehicle_share": 0.09},
        {"sensor_id": "cctv-kasturba-road", "corridor": "Kasturba Road", "vehicle_count_15m": 618, "heavy_vehicle_share": 0.04},
    ]


def advisories() -> list[dict[str, Any]]:
    configured = read_json_feed("public_advisories.json")
    if configured is not None:
        return configured

    return [
        {
            "id": "advisory-mg-road-rain",
            "corridor": "M G Road",
            "message": "Expect slow movement near Trinity circle due to rainwater accumulation.",
            "severity": "high",
            "issued_at": iso_at(-22),
        },
        {
            "id": "advisory-silk-board-crash",
            "corridor": "Outer Ring Road",
            "message": "Use Hosur Road service lanes while response teams clear the crash scene.",
            "severity": "high",
            "issued_at": iso_at(-10),
        },
    ]


def officer_statuses() -> list[dict[str, Any]]:
    configured = read_json_feed("officer_status.json")
    if configured is not None:
        return configured

    return [
        {"officer_id": "CBP-214", "station": "Cubbon Park", "status": "available", "last_seen": iso_at(-3)},
        {"officer_id": "CBP-319", "station": "Cubbon Park", "status": "deployed", "last_seen": iso_at(-5)},
        {"officer_id": "MAD-102", "station": "Madiwala", "status": "available", "last_seen": iso_at(-4)},
        {"officer_id": "HBL-087", "station": "Hebbal", "status": "available", "last_seen": iso_at(-7)},
    ]


def speed_context_for_corridor(corridor: Any) -> dict[str, Any]:
    corridor_key = str(corridor or "").strip().lower()
    for row in gps_speed_feed():
        if str(row.get("corridor", "")).strip().lower() == corridor_key:
            free_flow = max(float(row.get("free_flow_speed_kmph") or 0), 1.0)
            current = max(float(row.get("current_speed_kmph") or 0), 1.0)
            return {
                **row,
                "speed_ratio": min(current / free_flow, 1.0),
                "delay_factor": max(free_flow / current - 1.0, 0.0),
            }
    return {
        "corridor": corridor,
        "current_speed_kmph": None,
        "free_flow_speed_kmph": None,
        "sample_size": 0,
        "speed_ratio": 0.65,
        "delay_factor": 0.35,
    }


def sensor_context_for_corridor(corridor: Any) -> dict[str, Any]:
    corridor_key = str(corridor or "").strip().lower()
    matching = [
        row
        for row in sensor_counts()
        if str(row.get("corridor", "")).strip().lower() == corridor_key
    ]
    if not matching:
        return {"vehicle_count_15m": 0, "heavy_vehicle_share": 0.0, "sensor_count": 0}
    vehicle_count = sum(int(row.get("vehicle_count_15m") or 0) for row in matching)
    heavy_share = sum(float(row.get("heavy_vehicle_share") or 0.0) for row in matching) / len(matching)
    return {
        "vehicle_count_15m": vehicle_count,
        "heavy_vehicle_share": heavy_share,
        "sensor_count": len(matching),
    }


def operational_context_for_event(event_features: dict[str, Any]) -> dict[str, Any]:
    corridor = event_features.get("corridor")
    speed = speed_context_for_corridor(corridor)
    sensor = sensor_context_for_corridor(corridor)
    weather = weather_feed()
    relevant_advisories = [
        advisory
        for advisory in advisories()
        if str(advisory.get("corridor", "")).strip().lower() == str(corridor or "").strip().lower()
    ]
    return {
        "speed": speed,
        "weather": weather,
        "sensors": sensor,
        "advisories": relevant_advisories,
    }


def all_feed_records() -> dict[str, Any]:
    return {
        "live_incidents": live_incidents(),
        "planned_permits": planned_permits(),
        "gps_speeds": gps_speed_feed(),
        "weather": weather_feed(),
        "sensor_counts": sensor_counts(),
        "officer_statuses": officer_statuses(),
        "public_advisories": advisories(),
    }


def integration_status() -> list[dict[str, Any]]:
    observed = datetime.now(UTC)
    feeds = [
        ("ASTraM live incidents", "incident", len(live_incidents())),
        ("Planned permits", "permit", len(planned_permits())),
        ("Fleet GPS speeds", "mobility", len(gps_speed_feed())),
        ("Weather/rain/flooding", "weather", 1),
        ("CCTV/ANPR counts", "sensor", len(sensor_counts())),
        ("Officer mobile status", "field", len(officer_statuses())),
        ("Public advisories", "advisory", len(advisories())),
    ]
    return [
        FeedStatus(
            name=name,
            category=category,
            mode="local_adapter",
            records=records,
            last_seen=observed.isoformat(),
            freshness_seconds=0,
        ).as_dict()
        for name, category, records in feeds
    ]
