"""
Integration tests for the FastAPI application against a live PostgreSQL database.

These tests use the fixtures defined in conftest.py and are skipped automatically
when DATABASE_URL is not set.  In CI the postgres service container provides it.
"""

from datetime import timezone

import psycopg2.extras
import pytest


# ── Seed helpers ──────────────────────────────────────────────────────────────

def _insert_readings(conn, rows: list[dict]) -> None:
    with conn.cursor() as cur:
        psycopg2.extras.execute_values(
            cur,
            """
            INSERT INTO sensor_readings
                (id, timestamp, sensor_id, temperature, humidity, pressure, location)
            VALUES %s
            """,
            [
                (r["id"], r["timestamp"], r["sensor_id"],
                 r["temperature"], r["humidity"], r["pressure"], r["location"])
                for r in rows
            ],
        )
    conn.commit()


def _insert_anomaly(conn, sensor_data_id: int, sensor_id: str,
                    timestamp: str, anomaly_type: str, confidence: float) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO anomalies
                (sensor_data_id, sensor_id, timestamp, anomaly_type, confidence_score, detected_at)
            VALUES (%s, %s, %s, %s, %s, NOW())
            """,
            (sensor_data_id, sensor_id, timestamp, anomaly_type, confidence),
        )
    conn.commit()


def _reading(id: int, sensor_id: str, ts: str = "2024-01-01T00:00:00+00:00",
             temperature: float = 22.0) -> dict:
    return {
        "id": id,
        "timestamp": ts,
        "sensor_id": sensor_id,
        "temperature": temperature,
        "humidity": 50.0,
        "pressure": 1013.0,
        "location": "lab_a",
    }


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_ok_with_real_schema(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "db": "ok"}


# ── /sensors ─────────────────────────��───────────────────────────────���────────

def test_sensors_empty(client, db_conn):
    resp = client.get("/sensors")
    assert resp.status_code == 200
    assert resp.json() == []


def test_sensors_returns_correct_counts(client, db_conn):
    _insert_readings(db_conn, [
        _reading(1, "TEMP_001", "2024-01-01T00:00:00+00:00"),
        _reading(2, "TEMP_001", "2024-01-01T00:05:00+00:00"),
        _reading(3, "TEMP_001", "2024-01-01T00:10:00+00:00"),
        _reading(4, "HUMID_002", "2024-01-01T00:00:00+00:00"),
    ])
    resp = client.get("/sensors")
    assert resp.status_code == 200
    data = {row["sensor_id"]: row["reading_count"] for row in resp.json()}
    assert data["TEMP_001"] == 3
    assert data["HUMID_002"] == 1


# ── /anomalies ────────────────────────────────────────────────────────────────

def test_anomalies_empty(client, db_conn):
    resp = client.get("/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["results"] == []


def test_anomalies_returns_inserted_record(client, db_conn):
    _insert_readings(db_conn, [_reading(1, "TEMP_001", "2024-06-15T10:00:00+00:00", temperature=99.0)])
    _insert_anomaly(db_conn, 1, "TEMP_001", "2024-06-15T10:00:00+00:00", "temperature_anomaly", 4.5)

    resp = client.get("/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    row = body["results"][0]
    assert row["sensor_id"] == "TEMP_001"
    assert row["anomaly_type"] == "temperature_anomaly"
    assert abs(row["confidence_score"] - 4.5) < 1e-6


def test_anomalies_filter_by_sensor_id(client, db_conn):
    _insert_readings(db_conn, [
        _reading(1, "TEMP_001", "2024-01-01T00:00:00+00:00"),
        _reading(2, "HUMID_002", "2024-01-01T00:00:00+00:00"),
    ])
    _insert_anomaly(db_conn, 1, "TEMP_001", "2024-01-01T00:00:00+00:00", "temperature_anomaly", 3.1)
    _insert_anomaly(db_conn, 2, "HUMID_002", "2024-01-01T00:00:00+00:00", "humidity_anomaly", 2.5)

    resp = client.get("/anomalies?sensor_id=TEMP_001")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["results"][0]["sensor_id"] == "TEMP_001"


def test_anomalies_filter_by_date_range(client, db_conn):
    _insert_readings(db_conn, [
        _reading(1, "S1", "2024-01-01T00:00:00+00:00"),
        _reading(2, "S1", "2024-06-01T00:00:00+00:00"),
        _reading(3, "S1", "2024-12-01T00:00:00+00:00"),
    ])
    for rid, ts in [(1, "2024-01-01T00:00:00+00:00"),
                    (2, "2024-06-01T00:00:00+00:00"),
                    (3, "2024-12-01T00:00:00+00:00")]:
        _insert_anomaly(db_conn, rid, "S1", ts, "temperature_anomaly", 3.0)

    resp = client.get("/anomalies?start=2024-02-01T00:00:00Z&end=2024-11-01T00:00:00Z")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["results"][0]["sensor_data_id"] == 2


def test_anomalies_pagination(client, db_conn):
    readings = [_reading(i, "S1", f"2024-01-{i:02d}T00:00:00+00:00") for i in range(1, 16)]
    _insert_readings(db_conn, readings)
    for r in readings:
        _insert_anomaly(db_conn, r["id"], "S1", r["timestamp"], "temperature_anomaly", 3.0)

    page1 = client.get("/anomalies?page=1&page_size=10").json()
    page2 = client.get("/anomalies?page=2&page_size=10").json()

    assert page1["total"] == 15
    assert len(page1["results"]) == 10
    assert len(page2["results"]) == 5

    ids_p1 = {r["sensor_data_id"] for r in page1["results"]}
    ids_p2 = {r["sensor_data_id"] for r in page2["results"]}
    assert ids_p1.isdisjoint(ids_p2), "Pages must not overlap"
