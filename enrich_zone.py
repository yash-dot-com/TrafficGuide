from __future__ import annotations

import argparse
import os
import sys
from typing import Any

from sqlalchemy import create_engine, text

from env_loader import load_project_env


load_project_env()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill null event zones from nearby events using a PostGIS ST_DWithin query."
    )
    parser.add_argument(
        "--radius-meters",
        type=float,
        default=2000.0,
        help="Search radius for nearby events",
    )
    return parser.parse_args()


def require_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL is required, e.g. postgresql+psycopg2://user:pass@localhost/db")
    return database_url


def null_zone_count(connection: Any) -> int:
    return connection.execute(
        text("SELECT COUNT(*) FROM events WHERE zone IS NULL OR btrim(zone) = ''")
    ).scalar_one()


def backfill_zones(engine: Any, radius_meters: float) -> tuple[int, int, int]:
    update_sql = text(
        """
        WITH candidates AS (
            SELECT
                target.id AS event_id,
                nearby.zone AS zone,
                COUNT(*) AS zone_hits,
                AVG(ST_Distance(target.geom::geography, nearby.geom::geography)) AS avg_distance_meters
            FROM events AS target
            JOIN events AS nearby
                ON target.id <> nearby.id
                AND target.geom IS NOT NULL
                AND nearby.geom IS NOT NULL
                AND (target.zone IS NULL OR btrim(target.zone) = '')
                AND nearby.zone IS NOT NULL
                AND btrim(nearby.zone) <> ''
                AND ST_DWithin(target.geom::geography, nearby.geom::geography, :radius_meters)
            GROUP BY target.id, nearby.zone
        ),
        ranked AS (
            SELECT
                event_id,
                zone,
                ROW_NUMBER() OVER (
                    PARTITION BY event_id
                    ORDER BY zone_hits DESC, avg_distance_meters ASC, zone ASC
                ) AS zone_rank
            FROM candidates
        )
        UPDATE events AS event
        SET zone = ranked.zone
        FROM ranked
        WHERE event.id = ranked.event_id
            AND ranked.zone_rank = 1
        RETURNING event.id
        """
    )

    with engine.begin() as connection:
        before = null_zone_count(connection)
        updated = connection.execute(update_sql, {"radius_meters": radius_meters}).fetchall()
        after = null_zone_count(connection)

    return before, len(updated), after


def print_sanity(engine: Any) -> None:
    stats_sql = text(
        """
        SELECT
            COUNT(*) AS event_count,
            MIN(start_datetime) AS min_start,
            MAX(start_datetime) AS max_start,
            COUNT(*) FILTER (WHERE geom IS NOT NULL) AS events_with_geom,
            COUNT(*) FILTER (WHERE duration_minutes IS NULL) AS duration_nulls
        FROM events
        """
    )
    nulls_sql = text(
        """
        SELECT
            COUNT(*) FILTER (WHERE latitude IS NULL) AS latitude_nulls,
            COUNT(*) FILTER (WHERE longitude IS NULL) AS longitude_nulls,
            COUNT(*) FILTER (WHERE start_datetime IS NULL) AS start_datetime_nulls,
            COUNT(*) FILTER (WHERE zone IS NULL OR btrim(zone) = '') AS zone_nulls,
            COUNT(*) FILTER (WHERE police_station IS NULL OR btrim(police_station) = '') AS police_station_nulls,
            COUNT(*) FILTER (WHERE geom IS NULL) AS geom_nulls
        FROM events
        """
    )

    with engine.connect() as connection:
        stats = connection.execute(stats_sql).mappings().one()
        nulls = connection.execute(nulls_sql).mappings().one()
        station_count = connection.execute(text("SELECT COUNT(*) FROM police_stations")).scalar_one()

    print("\nSanity check")
    print(f"Events in table: {stats['event_count']}")
    print(f"Start date range: {stats['min_start']} -> {stats['max_start']}")
    print(f"Events with geometry: {stats['events_with_geom']}")
    print(f"Police stations seeded: {station_count}")
    print(f"Null duration_minutes: {stats['duration_nulls']}")
    print(
        "Null key columns: "
        f"latitude={nulls['latitude_nulls']}, "
        f"longitude={nulls['longitude_nulls']}, "
        f"start_datetime={nulls['start_datetime_nulls']}, "
        f"zone={nulls['zone_nulls']}, "
        f"police_station={nulls['police_station_nulls']}, "
        f"geom={nulls['geom_nulls']}"
    )


def main() -> None:
    args = parse_args()
    engine = create_engine(require_database_url(), future=True)
    before, updated, after = backfill_zones(engine, args.radius_meters)
    print(
        f"Zone enrichment complete: updated {updated} events "
        f"within {args.radius_meters:g}m (null/blank zones {before} -> {after})."
    )
    print_sanity(engine)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted")
