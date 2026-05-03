"""
Behavioral tests for AnomalyDetector against known data.

Each test uses a deterministic input sequence so the expected output can be
reasoned about without running the code.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import numpy as np
import pandas as pd
import pytest

from anomaly_detection import AnomalyDetector


# ── Helpers ───────────────────────────────────────────────────────────────────

def _records(sensor_id: str, temperatures: list, start_id: int = 1) -> list:
    base = pd.Timestamp("2024-01-01", tz="UTC")
    return [
        {
            "id": start_id + i,
            "timestamp": (base + pd.Timedelta(minutes=5 * i)).isoformat(),
            "sensor_id": sensor_id,
            "temperature": t,
            "humidity": 50.0,
            "pressure": 1013.0,
            "location": "lab",
        }
        for i, t in enumerate(temperatures)
    ]


def _temp_anomaly_ids(anomalies: list) -> set:
    return {a["sensor_data_id"] for a in anomalies if a["anomaly_type"] == "temperature_anomaly"}


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_clear_spike_is_detected():
    # 20 stable baseline readings followed by one large spike.
    baseline = [22.0] * 19 + [22.5]  # slight variation so std > 0
    spike = [80.0]
    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(_records("S1", baseline + spike))
    flagged = _temp_anomaly_ids(anomalies)
    assert 21 in flagged  # the spike (id=21) must be detected


def test_baseline_readings_not_flagged():
    # Only the spike should be flagged; the 20 preceding readings should not.
    baseline = [22.0 + 0.3 * (i % 3) for i in range(20)]
    spike = [100.0]
    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(_records("S1", baseline + spike))
    flagged = _temp_anomaly_ids(anomalies)
    baseline_ids = set(range(1, 21))
    assert not (flagged & baseline_ids), f"False positives in baseline: {flagged & baseline_ids}"
    assert 21 in flagged


def test_normal_variation_produces_no_anomalies():
    # Values oscillate well within two standard deviations — nothing should fire.
    values = [22.0 + 0.2 * (i % 5 - 2) for i in range(40)]  # range 21.6 – 22.4
    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(_records("S1", values))
    assert anomalies == [], f"Unexpected anomalies: {anomalies}"


def test_priors_only_window_z_score():
    """
    With shift(1) in place the z-score for a spike must equal
    (spike - prior_mean) / prior_std, computed from the 20 preceding readings
    only.  If the current reading were included in its own window both the mean
    and the std would shift, producing a different (lower) z-score.
    """
    baseline = [20.0 if i % 2 == 0 else 24.0 for i in range(20)]  # mean=22, std≈2.05
    spike = 28.0

    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(_records("S1", baseline + [spike]))

    temp_anomalies = [a for a in anomalies if a["anomaly_type"] == "temperature_anomaly"]
    assert len(temp_anomalies) == 1, "Spike should produce exactly one temperature anomaly"

    expected_z = abs(spike - np.mean(baseline)) / np.std(baseline, ddof=1)
    actual_z = temp_anomalies[0]["confidence_score"]
    assert abs(actual_z - expected_z) < 0.01, (
        f"z-score {actual_z:.4f} does not match priors-only expectation {expected_z:.4f}; "
        "shift(1) may not be in effect"
    )


def test_sensors_are_evaluated_independently():
    # Sensor B has a spike; sensor A does not. A should have zero anomalies.
    sensor_a = _records("A", [22.0 + 0.2 * (i % 3) for i in range(25)], start_id=1)
    baseline_b = [22.0 if i % 2 == 0 else 24.0 for i in range(20)]
    sensor_b = _records("B", baseline_b + [80.0], start_id=101)

    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(sensor_a + sensor_b)

    sensor_a_ids = {r["id"] for r in sensor_a}
    a_anomalies = [a for a in anomalies if a["sensor_data_id"] in sensor_a_ids]
    assert a_anomalies == [], f"Sensor A should be clean but got: {a_anomalies}"

    sensor_b_ids = {r["id"] for r in sensor_b}
    b_anomalies = [a for a in anomalies if a["sensor_data_id"] in sensor_b_ids]
    assert any(a["anomaly_type"] == "temperature_anomaly" for a in b_anomalies)


def test_no_anomalies_without_sufficient_prior_context():
    # A very short sequence (fewer readings than min_periods can resolve) should
    # not produce spurious anomalies even if values vary.
    values = [22.0, 50.0, 10.0]  # wild swings, but no prior window
    detector = AnomalyDetector(window_size=20, threshold=2.0)
    anomalies = detector.detect_anomalies(_records("S1", values))
    # With shift(1), row 0 has no prior at all (shifted value is NaN).
    # Rows 1 and 2 have 1-2 priors; std of 1-2 values is NaN or 0 → z is NaN → skipped.
    assert anomalies == [], f"Expected no anomalies from cold-start data, got: {anomalies}"
