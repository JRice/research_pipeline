"""
Smoke tests for the FastAPI application.

All database calls are mocked — no real Postgres required.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

# Set DATABASE_URL before importing main so get_conn() doesn't blow up.
os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")

from main import app, get_conn


# ── Mock DB factory ───────────────────────────────────────────────────────────

def _make_mock_conn(fetchone_return=None, fetchall_return=None):
    """Return a mock psycopg2 connection whose cursor honours fetchone/fetchall."""
    cur = MagicMock()
    cur.__enter__ = MagicMock(return_value=cur)
    cur.__exit__ = MagicMock(return_value=False)
    cur.fetchone.return_value = fetchone_return or {"count": 0}
    cur.fetchall.return_value = fetchall_return or []

    conn = MagicMock()
    conn.cursor.return_value = cur
    return conn


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_ok():
    mock_conn = _make_mock_conn()

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"

    app.dependency_overrides.clear()


def test_health_db_error_returns_503():
    mock_conn = _make_mock_conn()
    mock_conn.cursor.side_effect = Exception("connection refused")

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/health")
    assert resp.status_code == 503

    app.dependency_overrides.clear()


# ── /anomalies ────────────────────────────────────────────────────────────────

def test_anomalies_empty_db():
    mock_conn = _make_mock_conn(fetchone_return={"count": 0}, fetchall_return=[])

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    resp = client.get("/anomalies")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 0
    assert body["page"] == 1
    assert body["results"] == []

    app.dependency_overrides.clear()


def test_anomalies_pagination_params():
    mock_conn = _make_mock_conn(fetchone_return={"count": 200}, fetchall_return=[])

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    resp = client.get("/anomalies?page=3&page_size=10")
    assert resp.status_code == 200
    body = resp.json()
    assert body["page"] == 3
    assert body["page_size"] == 10

    app.dependency_overrides.clear()


def test_anomalies_page_size_cap():
    mock_conn = _make_mock_conn(fetchone_return={"count": 0}, fetchall_return=[])

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    # page_size > 200 should be rejected
    resp = client.get("/anomalies?page_size=500")
    assert resp.status_code == 422

    app.dependency_overrides.clear()


# ── /sensors ──────────────────────────────────────────────────────────────────

def test_sensors_empty_db():
    mock_conn = _make_mock_conn(fetchall_return=[])

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    resp = client.get("/sensors")
    assert resp.status_code == 200
    assert resp.json() == []

    app.dependency_overrides.clear()


def test_sensors_returns_list():
    rows = [
        {"sensor_id": "TEMP_001", "reading_count": 500},
        {"sensor_id": "HUMID_003", "reading_count": 250},
    ]
    mock_conn = _make_mock_conn(fetchall_return=rows)

    def override():
        yield mock_conn

    app.dependency_overrides[get_conn] = override
    client = TestClient(app)

    resp = client.get("/sensors")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["sensor_id"] == "TEMP_001"

    app.dependency_overrides.clear()
