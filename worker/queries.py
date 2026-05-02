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

# Truncate in dependency order (anomalies references sensor_readings).
TRUNCATE_TABLES = "TRUNCATE anomalies, sensor_readings"
