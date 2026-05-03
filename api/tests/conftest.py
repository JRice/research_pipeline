"""
Fixtures for integration tests that require a live PostgreSQL database.

All fixtures in this file are skipped automatically when DATABASE_URL is not
set, so the unit tests in test_main.py continue to run without Postgres.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import psycopg2
import psycopg2.extras
import pytest
from fastapi.testclient import TestClient

from main import app

_SCHEMA = os.path.join(os.path.dirname(__file__), "..", "..", "db", "init.sql")


@pytest.fixture(scope="session")
def _db_url():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL not set - integration tests skipped")
    return url


@pytest.fixture(scope="session")
def _apply_schema(_db_url):
    conn = psycopg2.connect(_db_url)
    with open(_SCHEMA) as f:
        with conn.cursor() as cur:
            cur.execute(f.read())
    conn.commit()
    conn.close()


@pytest.fixture
def db_conn(_apply_schema, _db_url):
    """Per-test connection. Truncates both tables on teardown."""
    conn = psycopg2.connect(_db_url, cursor_factory=psycopg2.extras.RealDictCursor)
    yield conn
    with conn.cursor() as cur:
        cur.execute("TRUNCATE anomalies, sensor_readings")
    conn.commit()
    conn.close()


@pytest.fixture
def client(_apply_schema):
    """TestClient that hits the real database (no dependency override)."""
    return TestClient(app)
