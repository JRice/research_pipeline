#!/usr/bin/env python3
"""
One-shot ingestion worker.

Flow: wait for Postgres -> optionally reset -> load CSV -> insert sensor_readings
      -> run anomaly detection (cold-start guarded) -> insert anomalies -> print summary.
"""

import argparse
import logging
import os
import sys
import time
from pathlib import Path
from typing import List, Tuple
from urllib.parse import urlparse

import boto3
import pandas as pd
import psycopg2
import psycopg2.extensions
from psycopg2.extras import execute_values
from dotenv import load_dotenv

# anomaly_detection.py is mounted into /app at runtime (see compose.yml).
# Do NOT rewrite this logic here.
from anomaly_detection import AnomalyDetector

from queries import INSERT_ANOMALIES, INSERT_READINGS, TRUNCATE_TABLES

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)


def wait_for_db(url: str, max_wait: int = 30) -> psycopg2.extensions.connection:
    """Retry until Postgres is accepting connections or max_wait seconds elapse."""
    deadline = time.time() + max_wait
    while True:
        try:
            conn = psycopg2.connect(url)
            logger.info("Connected to database")
            return conn
        except psycopg2.OperationalError as exc:
            if time.time() >= deadline:
                raise RuntimeError(f"Database not ready after {max_wait}s") from exc
            logger.info("Waiting for database ...")
            time.sleep(2)


def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="ISO8601", utc=True)
    return df


def download_s3_uri(s3_uri: str, dest: str = "/tmp/input.csv") -> str:
    parsed = urlparse(s3_uri)
    if parsed.scheme != "s3":
        raise ValueError(f"Expected s3:// URI, got: {s3_uri}")

    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise ValueError(f"Invalid S3 URI: {s3_uri}")

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    boto3.client("s3").download_file(bucket, key, dest)
    return dest


def resolve_input_csv() -> str:
    input_s3_uri = os.getenv("INPUT_S3_URI")
    input_csv = os.getenv("INPUT_CSV")

    if input_s3_uri:
        return download_s3_uri(input_s3_uri)
    if input_csv:
        return input_csv
    raise RuntimeError("Set INPUT_CSV for local runs or INPUT_S3_URI for AWS runs")


def _reading_tuples(df: pd.DataFrame) -> List[Tuple]:
    return [
        (
            int(r.id),
            r.timestamp.isoformat(),
            str(r.sensor_id),
            float(r.temperature),
            float(r.humidity),
            float(r.pressure),
            str(r.location),
        )
        for r in df.itertuples(index=False)
    ]


def insert_readings(conn: psycopg2.extensions.connection, df: pd.DataFrame) -> int:
    rows = _reading_tuples(df)
    with conn.cursor() as cur:
        returned = execute_values(cur, INSERT_READINGS, rows, fetch=True)
    conn.commit()
    return len(returned)


def filter_eligible_sensors(df: pd.DataFrame, window_size: int) -> pd.DataFrame:
    """Return only rows for sensors that have >= window_size readings in this batch."""
    counts = df.groupby("sensor_id").size()
    eligible_ids = counts[counts >= window_size].index
    return df[df["sensor_id"].isin(eligible_ids)].copy()


def _anomaly_tuples(anomalies: List[dict], df: pd.DataFrame) -> List[Tuple]:
    """Enrich raw anomaly dicts with denormalized sensor_id/timestamp from the batch."""
    lookup = df.set_index("id")[["sensor_id", "timestamp"]].to_dict("index")
    rows: List[Tuple] = []
    for a in anomalies:
        src = lookup.get(a["sensor_data_id"])
        if src is None:
            continue
        ts = src["timestamp"]
        ts_str = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
        rows.append((
            int(a["sensor_data_id"]),
            str(src["sensor_id"]),
            ts_str,
            str(a["anomaly_type"]),
            float(a["confidence_score"]),
            str(a["detected_at"]),
        ))
    return rows


def insert_anomalies(conn: psycopg2.extensions.connection, rows: List[Tuple]) -> int:
    if not rows:
        return 0
    with conn.cursor() as cur:
        returned = execute_values(cur, INSERT_ANOMALIES, rows, fetch=True)
    conn.commit()
    return len(returned)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest sensor CSV into PostgreSQL.")
    parser.add_argument(
        "csv_path",
        nargs="?",
        help="Path to the CSV file (overrides INPUT_CSV / INPUT_S3_URI)",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Truncate both tables before inserting (useful during development)",
    )
    args = parser.parse_args()

    csv_path = args.csv_path or resolve_input_csv()

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set")

    start = time.time()
    conn = wait_for_db(url)

    if args.reset:
        logger.info("Resetting tables ...")
        with conn.cursor() as cur:
            cur.execute(TRUNCATE_TABLES)
        conn.commit()

    logger.info("Loading %s ...", csv_path)
    df = load_csv(csv_path)
    logger.info("Loaded %d rows", len(df))

    readings_inserted = insert_readings(conn, df)

    detector = AnomalyDetector()
    eligible = filter_eligible_sensors(df, detector.window_size)
    skipped = set(df["sensor_id"].unique()) - set(eligible["sensor_id"].unique())
    if skipped:
        logger.warning(
            "Skipping anomaly detection for sensors with < %d readings: %s",
            detector.window_size,
            skipped,
        )

    raw_anomalies: List[dict] = []
    if not eligible.empty:
        raw_anomalies = detector.detect_anomalies(eligible.to_dict("records"))

    anom_rows = _anomaly_tuples(raw_anomalies, eligible)
    anomalies_inserted = insert_anomalies(conn, anom_rows)
    conn.close()

    elapsed = time.time() - start
    print("\nIngest complete:")
    print(f"  Readings inserted : {readings_inserted}")
    print(f"  Anomalies inserted: {anomalies_inserted}")
    print(f"  Elapsed           : {elapsed:.2f}s")


if __name__ == "__main__":
    main()
