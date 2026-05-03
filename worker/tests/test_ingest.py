"""
Smoke tests for ingest.py logic without a real database or S3 dependency.
"""

import os
import sys
from pathlib import Path

# Allow importing worker modules directly when running pytest from repo root.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd
import pytest

from ingest import (
    _anomaly_tuples,
    download_s3_uri,
    resolve_input_csv,
)


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
            "temperature": 45.0,
            "humidity": 50.5,
            "pressure": 1013.1,
            "location": "lab_a",
        },
    ])


def test_anomaly_tuples_populates_sensor_id():
    df = _base_df()
    anomalies = [
        {
            "sensor_data_id": 2,
            "anomaly_type": "temperature_anomaly",
            "confidence_score": 3.2,
            "detected_at": "2024-01-01T00:06:00",
        },
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert len(rows) == 1
    sensor_data_id, sensor_id, timestamp, anomaly_type, confidence, detected_at = rows[0]
    assert sensor_data_id == 2
    assert sensor_id == "TEMP_001"
    assert "2024-01-01" in timestamp
    assert anomaly_type == "temperature_anomaly"
    assert abs(confidence - 3.2) < 1e-9
    assert detected_at == "2024-01-01T00:06:00"


def test_anomaly_tuples_skips_unknown_ids():
    df = _base_df()
    anomalies = [
        {
            "sensor_data_id": 999,
            "anomaly_type": "temperature_anomaly",
            "confidence_score": 2.1,
            "detected_at": "2024-01-01T00:06:00",
        },
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert rows == []


def test_anomaly_tuples_handles_multiple():
    df = _base_df()
    anomalies = [
        {
            "sensor_data_id": 1,
            "anomaly_type": "humidity_anomaly",
            "confidence_score": 2.5,
            "detected_at": "2024-01-01T00:01:00",
        },
        {
            "sensor_data_id": 2,
            "anomaly_type": "temperature_anomaly",
            "confidence_score": 3.1,
            "detected_at": "2024-01-01T00:06:00",
        },
    ]
    rows = _anomaly_tuples(anomalies, df)
    assert len(rows) == 2


def test_download_s3_uri_downloads_to_destination(monkeypatch, tmp_path):
    calls = []

    class FakeS3Client:
        def download_file(self, bucket, key, dest):
            calls.append((bucket, key, dest))
            Path(dest).write_text("ok", encoding="utf-8")

    monkeypatch.setattr("ingest.boto3.client", lambda service: FakeS3Client())

    dest = tmp_path / "nested" / "input.csv"
    result = download_s3_uri("s3://my-bucket/path/to/file.csv", str(dest))

    assert result == str(dest)
    assert calls == [("my-bucket", "path/to/file.csv", str(dest))]
    assert dest.read_text(encoding="utf-8") == "ok"


@pytest.mark.parametrize("uri", ["https://example.com/file.csv", "s3://", "s3://bucket"])
def test_download_s3_uri_rejects_invalid_uris(uri):
    with pytest.raises(ValueError):
        download_s3_uri(uri)


def test_resolve_input_csv_prefers_s3(monkeypatch):
    monkeypatch.setenv("INPUT_S3_URI", "s3://bucket/sample.csv")
    monkeypatch.setenv("INPUT_CSV", "/data/local.csv")
    monkeypatch.setattr("ingest.download_s3_uri", lambda uri: "/tmp/input.csv")

    assert resolve_input_csv() == "/tmp/input.csv"


def test_resolve_input_csv_falls_back_to_local(monkeypatch):
    monkeypatch.delenv("INPUT_S3_URI", raising=False)
    monkeypatch.setenv("INPUT_CSV", "/data/local.csv")

    assert resolve_input_csv() == "/data/local.csv"


def test_resolve_input_csv_requires_configuration(monkeypatch):
    monkeypatch.delenv("INPUT_S3_URI", raising=False)
    monkeypatch.delenv("INPUT_CSV", raising=False)

    with pytest.raises(RuntimeError):
        resolve_input_csv()
