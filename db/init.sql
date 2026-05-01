-- Sensor readings: raw data from CSV ingestion
CREATE TABLE IF NOT EXISTS sensor_readings (
    id          INT         PRIMARY KEY,
    timestamp   TIMESTAMPTZ NOT NULL,
    sensor_id   VARCHAR     NOT NULL,
    temperature FLOAT,
    humidity    FLOAT,
    pressure    FLOAT,
    location    VARCHAR
);

CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_timestamp
    ON sensor_readings (sensor_id, timestamp);

-- Anomalies: detected by the rolling-window algorithm.
-- sensor_id and timestamp are denormalized to avoid a join on every API query.
CREATE TABLE IF NOT EXISTS anomalies (
    id               SERIAL      PRIMARY KEY,
    sensor_data_id   INT         NOT NULL REFERENCES sensor_readings (id),
    sensor_id        VARCHAR     NOT NULL,
    timestamp        TIMESTAMPTZ NOT NULL,
    anomaly_type     VARCHAR     NOT NULL,
    confidence_score FLOAT,
    detected_at      TIMESTAMPTZ,
    UNIQUE (sensor_data_id, anomaly_type)
);

CREATE INDEX IF NOT EXISTS idx_anomalies_sensor_timestamp
    ON anomalies (sensor_id, timestamp);
