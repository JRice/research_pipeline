"""
Smoke tests for ingest.py logic — no database required.

Tests:
  - filter_eligible_sensors: cold-start guard drops sensors below window_size
  - _anomaly_tuples: correctly maps anomaly dicts to DB-ready rows
"""

import sys
import os

# Allow importing worker modules directly when running pytest from repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
# anomaly_detection.py lives at repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pandas as pd
import pytest

from ingest import _anomaly_tuples, filter_eligible_sensors


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_df(sensor_counts: dict) -> pd.DataFrame:
    """Build a minimal DataFrame with the given number of rows per sensor."""
    rows = []
    row_id = 1
    for sensor_id, count in sensor_counts.items():
        for i in range(count):
            rows.append({
                "id": row_id,
                "sensor_id": sensor_id,
                "timestamp": pd.Timestamp("2024-01-01", tz="UTC") + pd.Timedelta(minutes=5 * i),
                "temperature": 22.0,
                "humidity": 50.0,
                "pressure": 1013.0,
                "location": "lab",
            })
            row_id += 1
    return pd.DataFrame(rows)


# ── filter_eligible_sensors ───────────────────────────────────────────────────

def test_short_sensor_is_excluded():
    df = _make_df({"LONG": 25, "SHORT": 5})
    result = filter_eligible_sensors(df, window_size=20)
    assert "LONG" in result["sensor_id"].values
    assert "SHORT" not in result["sensor_id"].values


def test_sensor_exactly_at_threshold_is_included():
    df = _make_df({"AT_THRESHOLD": 20})
    result = filter_eligible_sensors(df, window_size=20)
    assert len(result) == 20


def test_all_sensors_short_returns_empty():
    df = _make_df({"A": 3, "B": 7})
    result = filter_eligible_sensors(df, window_size=20)
    assert result.empty


def test_original_df_is_not_mutated():
    df = _make_df({"GOOD": 30, "BAD": 2})
    original_len = len(df)
    filter_eligible_sensors(df, window_size=20)
    assert len(df) == original_len


# ── _anomaly_tuples ───────────────────────────────────────────────────────────

def _base_df() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "id": 1,
            "sensor_id": "TEMP_001",
            "timestamp": pd.Timestamp("2024-01-01T00:00:00", tz="UTC"),
            "temperature": 22.0,
            "humidity": 50.0,
            "pressure": 1013.0,
            "location": "lab_a",
        },
        {
            "id": 2,
            "sensor_id": "TEMP_001",
            "timestamp": pd.Timestamp("2024-01-01T00:05:00", tz="UTC"),
            "temperature": 45.0,  # spike
            "humidity": 50.5,
            "pressure": 1013.1,
            "location": "lab_a",
        },
    ])


def test_anomaly_tuples_populates_sensor_id():
    df = _base_df()
    anomalies = [
        {"sensor_data_id": 2, "anomaly_type": "temperature_anomaly",
         "confidence_score": 3.2, "detected_at": "2024-01-01T00:06:00"},
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert len(rows) == 1
    sensor_data_id, sensor_id, timestamp, anomaly_type, confidence, detected_at = rows[0]
    assert sensor_data_id == 2
    assert sensor_id == "TEMP_001"
    assert "2024-01-01" in timestamp
    assert anomaly_type == "temperature_anomaly"
    assert abs(confidence - 3.2) < 1e-9


def test_anomaly_tuples_skips_unknown_ids():
    df = _base_df()
    anomalies = [
        {"sensor_data_id": 999, "anomaly_type": "temperature_anomaly",
         "confidence_score": 2.1, "detected_at": "2024-01-01T00:06:00"},
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert rows == []


def test_anomaly_tuples_handles_multiple():
    df = _base_df()
    anomalies = [
        {"sensor_data_id": 1, "anomaly_type": "humidity_anomaly",
         "confidence_score": 2.5, "detected_at": "2024-01-01T00:01:00"},
        {"sensor_data_id": 2, "anomaly_type": "temperature_anomaly",
         "confidence_score": 3.1, "detected_at": "2024-01-01T00:06:00"},
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert len(rows) == 2
