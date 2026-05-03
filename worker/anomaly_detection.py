#!/usr/bin/env python3
"""
Simple anomaly detection algorithm for sensor data.
Candidates can use this as-is or adapt it for their solution.

Algorithm: Flags readings that are >2 standard deviations from the rolling mean
Rolling window: 20 readings per sensor per metric
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, window_size: int = 20, threshold: float = 2.0):
        """
        Initialize anomaly detector.

        Args:
            window_size: Number of previous readings to use for rolling statistics
            threshold: Number of standard deviations to consider anomalous
        """
        self.window_size = window_size
        self.threshold = threshold
        self.metrics = ['temperature', 'humidity', 'pressure']

    def detect_anomalies(self, sensor_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Detect anomalies in sensor data.

        Args:
            sensor_data: List of sensor reading dictionaries with keys:
                        id, timestamp, sensor_id, temperature, humidity, pressure, location

        Returns:
            List of anomaly dictionaries with keys:
                sensor_data_id, anomaly_type, confidence_score, detected_at
        """
        if not sensor_data:
            return []

        # Convert to DataFrame for easier processing
        df = pd.DataFrame(sensor_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values(['sensor_id', 'timestamp'])

        anomalies = []

        # Process each sensor separately
        for sensor_id in df['sensor_id'].unique():
            sensor_df = df[df['sensor_id'] == sensor_id].copy()

            # Calculate rolling statistics for each metric
            for metric in self.metrics:
                if metric not in sensor_df.columns:
                    continue

                # Calculate rolling mean and std over prior readings only
                # (shift(1) excludes the current point so a spike can't dampen its own z-score)
                rolling_mean = sensor_df[metric].shift(1).rolling(
                    window=self.window_size,
                    min_periods=4
                ).mean()

                rolling_std = sensor_df[metric].shift(1).rolling(
                    window=self.window_size,
                    min_periods=4
                ).std()

                # Calculate z-scores
                z_scores = (sensor_df[metric] - rolling_mean) / rolling_std

                # Find anomalies (z-score > threshold)
                anomaly_mask = np.abs(z_scores) > self.threshold

                # Create anomaly records
                for idx in sensor_df[anomaly_mask].index:
                    row = sensor_df.loc[idx]
                    z_score = z_scores.loc[idx]

                    # Skip if z_score is NaN (not enough data points)
                    if pd.isna(z_score):
                        continue

                    anomaly = {
                        'sensor_data_id': row['id'],
                        'anomaly_type': f'{metric}_anomaly',
                        'confidence_score': abs(z_score),
                        'detected_at': pd.Timestamp.now().isoformat()
                    }
                    anomalies.append(anomaly)

        logger.info(f"Detected {len(anomalies)} anomalies in {len(sensor_data)} readings")
        return anomalies

    def process_batch(self, sensor_data: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Process a batch of sensor data and return both cleaned data and anomalies.

        Args:
            sensor_data: Raw sensor readings

        Returns:
            Dictionary with 'data' (cleaned readings) and 'anomalies' keys
        """
        anomalies = self.detect_anomalies(sensor_data)

        # Mark anomalous readings (optional: you might want to keep all data)
        anomalous_ids = {a['sensor_data_id'] for a in anomalies}

        return {
            'data': sensor_data,  # Keep all data
            'anomalies': anomalies,
            'anomalous_reading_ids': list(anomalous_ids)
        }


def example_usage():
    """Example of how to use the anomaly detector."""

    # Sample data (matches the CSV format)
    sample_data = [
        {'id': 1, 'timestamp': '2024-01-01T00:00:00Z', 'sensor_id': 'TEMP_001',
         'temperature': 22.5, 'humidity': 45.2, 'pressure': 1013.25, 'location': 'lab_a'},
        {'id': 2, 'timestamp': '2024-01-01T00:05:00Z', 'sensor_id': 'TEMP_001',
         'temperature': 22.7, 'humidity': 45.8, 'pressure': 1013.20, 'location': 'lab_a'},
        {'id': 3, 'timestamp': '2024-01-01T00:10:00Z', 'sensor_id': 'TEMP_001',
         'temperature': 35.8, 'humidity': 46.1, 'pressure': 1013.15, 'location': 'lab_a'},  # Anomaly!
        {'id': 4, 'timestamp': '2024-01-01T00:15:00Z', 'sensor_id': 'TEMP_001',
         'temperature': 22.9, 'humidity': 45.5, 'pressure': 1013.25, 'location': 'lab_a'},
    ]

    # Create detector and process data
    detector = AnomalyDetector()
    result = detector.process_batch(sample_data)

    print("Detected anomalies:")
    for anomaly in result['anomalies']:
        print(f"  - {anomaly['anomaly_type']}: ID {anomaly['sensor_data_id']}, "
              f"confidence {anomaly['confidence_score']:.2f}")


if __name__ == "__main__":
    example_usage()
