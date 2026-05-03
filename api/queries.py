"""SQL query constants for the FastAPI application."""

HEALTH_CHECK = """
    SELECT COUNT(*) AS tables_ready
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name IN ('sensor_readings', 'anomalies')
"""

GET_SENSORS = """
    SELECT sensor_id, COUNT(*) AS reading_count
    FROM sensor_readings
    GROUP BY sensor_id
    ORDER BY sensor_id
"""

# Base SELECT for anomalies - a WHERE clause and ORDER/LIMIT/OFFSET are appended
# dynamically in main.py using safe parameterised queries.
# location is fetched via a single join; sensor_id and timestamp filters use the
# denormalized anomalies columns so no join is needed for filtering.
ANOMALY_SELECT_BASE = """
    SELECT
        a.id,
        a.sensor_data_id,
        a.sensor_id,
        a.timestamp,
        sr.location,
        a.anomaly_type,
        a.confidence_score,
        a.detected_at
    FROM anomalies a
    LEFT JOIN sensor_readings sr ON sr.id = a.sensor_data_id
"""

ANOMALY_COUNT_BASE = """
    SELECT COUNT(*) AS count
    FROM anomalies a
"""
