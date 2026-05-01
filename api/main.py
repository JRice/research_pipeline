"""
FastAPI application — sensor anomaly pipeline.

Endpoints
---------
GET  /health      liveness + database check
GET  /anomalies   paginated anomaly query (filter by sensor_id, date range)
GET  /sensors     distinct sensor IDs with reading counts
POST /ingest      convenience trigger — runs the worker via docker compose run
"""

import logging
import os
import subprocess
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

import psycopg2
import psycopg2.extensions
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from queries import (
    ANOMALY_COUNT_BASE,
    ANOMALY_SELECT_BASE,
    GET_SENSORS,
    HEALTH_CHECK,
)

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="Sensor Pipeline API", version="1.0.0")


# ── Database dependency ───────────────────────────────────────────────────────

def get_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")
    conn = psycopg2.connect(url, cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        yield conn
    finally:
        conn.close()


# ── Query builder ─────────────────────────────────────────────────────────────

def _anomaly_where(
    sensor_id: Optional[str],
    start: Optional[datetime],
    end: Optional[datetime],
) -> Tuple[str, list]:
    """Return (WHERE clause, params list) for the given optional filters."""
    clauses: List[str] = []
    params: List[Any] = []

    if sensor_id is not None:
        clauses.append("a.sensor_id = %s")
        params.append(sensor_id)
    if start is not None:
        clauses.append("a.timestamp >= %s")
        params.append(start)
    if end is not None:
        clauses.append("a.timestamp <= %s")
        params.append(end)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
def health(conn: psycopg2.extensions.connection = Depends(get_conn)) -> Dict[str, str]:
    try:
        with conn.cursor() as cur:
            cur.execute(HEALTH_CHECK)
        return {"status": "ok", "db": "ok"}
    except Exception as exc:
        logger.error("Health check DB query failed: %s", exc)
        raise HTTPException(
            status_code=503,
            detail={"status": "error", "db": str(exc)},
        )


@app.get("/anomalies")
def list_anomalies(
    sensor_id: Optional[str] = Query(None, description="Filter by sensor ID"),
    start: Optional[datetime] = Query(None, description="ISO datetime lower bound (inclusive)"),
    end: Optional[datetime] = Query(None, description="ISO datetime upper bound (inclusive)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    conn: psycopg2.extensions.connection = Depends(get_conn),
) -> Dict[str, Any]:
    where, params = _anomaly_where(sensor_id, start, end)
    offset = (page - 1) * page_size

    with conn.cursor() as cur:
        cur.execute(f"{ANOMALY_COUNT_BASE} {where}", params)
        total: int = cur.fetchone()["count"]

        cur.execute(
            f"{ANOMALY_SELECT_BASE} {where} ORDER BY a.timestamp DESC LIMIT %s OFFSET %s",
            params + [page_size, offset],
        )
        results = [dict(row) for row in cur.fetchall()]

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "results": results,
    }


@app.get("/sensors")
def list_sensors(
    conn: psycopg2.extensions.connection = Depends(get_conn),
) -> List[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(GET_SENSORS)
        return [dict(row) for row in cur.fetchall()]


# ── Ingest trigger ────────────────────────────────────────────────────────────
# Convenience endpoint for demo purposes only.
# Requires /var/run/docker.sock and the compose file to be mounted into this
# container (see compose.yml api.volumes).

def _run_worker() -> None:
    compose_file = os.environ.get("COMPOSE_FILE", "/app/compose.yml")
    cmd = ["docker", "compose", "-f", compose_file, "run", "--rm", "worker"]
    logger.info("Triggering worker: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            logger.error("Worker exited %d:\n%s", result.returncode, result.stderr)
        else:
            logger.info("Worker completed successfully")
    except FileNotFoundError:
        logger.error(
            "docker CLI not found — the API container needs docker.io installed "
            "and /var/run/docker.sock mounted"
        )


@app.post("/ingest", status_code=202)
def trigger_ingest() -> Dict[str, str]:
    job_id = str(uuid.uuid4())
    thread = threading.Thread(target=_run_worker, daemon=True)
    thread.start()
    return {"job_id": job_id, "status": "accepted"}
