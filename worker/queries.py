"""SQL query constants for the ingestion worker."""

INSERT_READINGS = """
    INSERT INTO sensor_readings
        (id, timestamp, sensor_id, temperature, humidity, pressure, location)
    VALUES %s
    ON CONFLICT (id) DO NOTHING
    RETURNING id
"""

INSERT_ANOMALIES = """
    INSERT INTO anomalies
        (sensor_data_id, sensor_id, timestamp, anomaly_type, confidence_score, detected_at)
    VALUES %s
    ON CONFLICT (sensor_data_id, anomaly_type) DO NOTHING
    RETURNING id
"""

# Fetch the most recent `window_size` rows per sensor, excluding the just-inserted batch.
# Used to build the rolling-window context before running anomaly detection.
FETCH_PRIOR_HISTORY = """
    WITH ranked AS (
        SELECT id, timestamp, sensor_id, temperature, humidity, pressure, location,
               ROW_NUMBER() OVER (PARTITION BY sensor_id ORDER BY timestamp DESC) AS rn
        FROM sensor_readings
        WHERE sensor_id = ANY(%s)
          AND id != ALL(%s)
    )
    SELECT id, timestamp, sensor_id, temperature, humidity, pressure, location
    FROM ranked
    WHERE rn <= %s
    ORDER BY sensor_id, timestamp
"""

# Truncate in dependency order (anomalies references sensor_readings).
TRUNCATE_TABLES = "TRUNCATE anomalies, sensor_readings"
