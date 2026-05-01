#!/usr/bin/env python3
"""
Sample data generator for research sensor readings.
Creates realistic time-series data with controllable anomalies.

Usage:
    python generate_data.py --observations 1000 --output sample_data.csv
    python generate_data.py -n 50000 -o large_dataset.csv --anomaly-rate 0.05
    python generate_data.py --help

The script generates data for multiple sensors with realistic baselines and
injects various types of anomalies (spikes, drifts, sensor failures).
"""

import argparse
import csv
import random
import math
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import numpy as np

# Sensor configurations with realistic baselines
SENSOR_CONFIGS = [
    {
        'sensor_id': 'TEMP_001',
        'location': 'lab_a',
        'temp_baseline': 22.0,
        'humid_baseline': 45.0,
        'press_baseline': 1013.25
    },
    {
        'sensor_id': 'TEMP_002',
        'location': 'lab_b',
        'temp_baseline': 21.5,
        'humid_baseline': 50.0,
        'press_baseline': 1012.80
    },
    {
        'sensor_id': 'HUMID_003',
        'location': 'greenhouse',
        'temp_baseline': 26.0,
        'humid_baseline': 75.0,
        'press_baseline': 1011.50
    },
    {
        'sensor_id': 'PRESS_004',
        'location': 'outdoor',
        'temp_baseline': 18.0,
        'humid_baseline': 60.0,
        'press_baseline': 1015.00
    },
    {
        'sensor_id': 'MULTI_005',
        'location': 'server_room',
        'temp_baseline': 20.0,
        'humid_baseline': 35.0,
        'press_baseline': 1013.00
    }
]

class DataGenerator:
    def __init__(self, anomaly_rate: float = 0.03, seed: int = None):
        """
        Initialize the data generator.

        Args:
            anomaly_rate: Fraction of readings that should be anomalous (0.0 to 1.0)
            seed: Random seed for reproducible data generation
        """
        self.anomaly_rate = anomaly_rate
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)

        # Anomaly types and their characteristics
        self.anomaly_types = [
            'spike_high',      # Sudden spike upward
            'spike_low',       # Sudden spike downward
            'drift_up',        # Gradual increase over time
            'drift_down',      # Gradual decrease over time
            'sensor_failure',  # Readings stuck at same value
            'noise_burst'      # High frequency noise
        ]

    def generate_normal_reading(self, sensor: Dict, timestamp: datetime,
                              prev_reading: Dict = None) -> Dict[str, Any]:
        """Generate a normal (non-anomalous) sensor reading."""

        # Add some natural variation and temporal correlation
        temp_noise = np.random.normal(0, 0.5)
        humid_noise = np.random.normal(0, 2.0)
        press_noise = np.random.normal(0, 0.3)

        # Add slight temporal correlation if previous reading exists
        if prev_reading:
            temp_correlation = 0.7 * (prev_reading['temperature'] - sensor['temp_baseline'])
            humid_correlation = 0.6 * (prev_reading['humidity'] - sensor['humid_baseline'])
            press_correlation = 0.8 * (prev_reading['pressure'] - sensor['press_baseline'])
        else:
            temp_correlation = humid_correlation = press_correlation = 0

        # Add daily cycle (temperature varies more during day)
        hour_of_day = timestamp.hour
        daily_temp_cycle = 2.0 * math.sin(2 * math.pi * (hour_of_day - 6) / 24)

        return {
            'timestamp': timestamp.isoformat() + 'Z',
            'sensor_id': sensor['sensor_id'],
            'temperature': round(sensor['temp_baseline'] + daily_temp_cycle +
                               temp_correlation * 0.3 + temp_noise, 1),
            'humidity': round(max(0, min(100, sensor['humid_baseline'] +
                                       humid_correlation * 0.3 + humid_noise)), 1),
            'pressure': round(sensor['press_baseline'] +
                            press_correlation * 0.3 + press_noise, 2),
            'location': sensor['location']
        }

    def inject_anomaly(self, normal_reading: Dict, anomaly_type: str) -> Dict[str, Any]:
        """Inject a specific type of anomaly into a normal reading."""

        reading = normal_reading.copy()

        if anomaly_type == 'spike_high':
            # Random metric gets a high spike
            metric = random.choice(['temperature', 'humidity', 'pressure'])
            if metric == 'temperature':
                reading[metric] += random.uniform(10, 25)
            elif metric == 'humidity':
                reading[metric] = min(100, reading[metric] + random.uniform(20, 40))
            else:  # pressure
                reading[metric] += random.uniform(15, 50)

        elif anomaly_type == 'spike_low':
            # Random metric gets a low spike
            metric = random.choice(['temperature', 'humidity', 'pressure'])
            if metric == 'temperature':
                reading[metric] -= random.uniform(8, 20)
            elif metric == 'humidity':
                reading[metric] = max(0, reading[metric] - random.uniform(15, 35))
            else:  # pressure
                reading[metric] -= random.uniform(20, 60)

        elif anomaly_type == 'sensor_failure':
            # All metrics stuck at unrealistic values
            reading['temperature'] = -999.0
            reading['humidity'] = 0.0
            reading['pressure'] = 0.0

        elif anomaly_type == 'noise_burst':
            # High frequency noise on all metrics
            reading['temperature'] += random.uniform(-5, 5)
            reading['humidity'] += random.uniform(-10, 10)
            reading['pressure'] += random.uniform(-8, 8)

        elif anomaly_type in ['drift_up', 'drift_down']:
            # Gradual drift (will be applied over multiple readings)
            multiplier = 1.5 if anomaly_type == 'drift_up' else -1.5
            reading['temperature'] += multiplier * random.uniform(1, 3)
            reading['humidity'] += multiplier * random.uniform(2, 8)
            reading['pressure'] += multiplier * random.uniform(1, 4)

        # Ensure values stay within realistic bounds
        reading['temperature'] = max(-50, min(60, reading['temperature']))
        reading['humidity'] = max(0, min(100, reading['humidity']))
        reading['pressure'] = max(800, min(1100, reading['pressure']))

        return reading

    def generate_dataset(self, num_observations: int,
                        start_time: datetime = None) -> List[Dict[str, Any]]:
        """
        Generate a complete dataset with the specified number of observations.

        Args:
            num_observations: Total number of sensor readings to generate
            start_time: Starting timestamp (defaults to 24 hours ago)

        Returns:
            List of sensor reading dictionaries
        """

        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(hours=24)

        dataset = []
        sensors = SENSOR_CONFIGS.copy()

        # Calculate readings per sensor and time interval
        readings_per_sensor = num_observations // len(sensors)
        time_interval_minutes = (24 * 60) // readings_per_sensor  # Spread over 24 hours

        # Track previous readings for temporal correlation
        prev_readings = {sensor['sensor_id']: None for sensor in sensors}

        # Generate anomaly schedule
        total_anomalies = int(num_observations * self.anomaly_rate)
        anomaly_indices = set(random.sample(range(num_observations), total_anomalies))

        observation_id = 1
        current_time = start_time

        for i in range(num_observations):
            # Round-robin through sensors
            sensor = sensors[i % len(sensors)]

            # Generate base reading
            reading = self.generate_normal_reading(
                sensor, current_time, prev_readings[sensor['sensor_id']]
            )

            # Inject anomaly if scheduled
            if i in anomaly_indices:
                anomaly_type = random.choice(self.anomaly_types)
                reading = self.inject_anomaly(reading, anomaly_type)

            # Add database ID
            reading['id'] = observation_id

            # Store for temporal correlation
            prev_readings[sensor['sensor_id']] = reading

            dataset.append(reading)
            observation_id += 1

            # Advance time (with some jitter)
            jitter = random.uniform(-0.3, 0.3) * time_interval_minutes
            current_time += timedelta(minutes=time_interval_minutes + jitter)

        # Sort by timestamp for realistic time series
        dataset.sort(key=lambda x: x['timestamp'])

        return dataset

def save_to_csv(dataset: List[Dict[str, Any]], filename: str):
    """Save dataset to CSV file."""

    if not dataset:
        print("No data to save!")
        return

    fieldnames = ['id', 'timestamp', 'sensor_id', 'temperature', 'humidity', 'pressure', 'location']

    with open(filename, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(dataset)

    print(f"Generated {len(dataset)} observations saved to {filename}")

def main():
    parser = argparse.ArgumentParser(
        description='Generate sample sensor data with controllable anomalies',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -n 1000 -o test_data.csv
  %(prog)s --observations 50000 --output large_test.csv --anomaly-rate 0.05
  %(prog)s -n 500 --seed 42 --anomaly-rate 0.1
        """
    )

    parser.add_argument('-n', '--observations', type=int, default=1000,
                       help='Number of sensor observations to generate (default: 1000)')
    parser.add_argument('-o', '--output', default='sample_data.csv',
                       help='Output CSV filename (default: sample_data.csv)')
    parser.add_argument('--anomaly-rate', type=float, default=0.03,
                       help='Fraction of readings that should be anomalous (default: 0.03)')
    parser.add_argument('--seed', type=int,
                       help='Random seed for reproducible generation')
    parser.add_argument('--start-time',
                       help='Starting timestamp (ISO format, default: 24 hours ago)')

    args = parser.parse_args()

    # Validate arguments
    if args.observations <= 0:
        parser.error("Number of observations must be positive")
    if not 0 <= args.anomaly_rate <= 1:
        parser.error("Anomaly rate must be between 0 and 1")

    # Parse start time if provided
    start_time = None
    if args.start_time:
        try:
            start_time = datetime.fromisoformat(args.start_time.replace('Z', '+00:00'))
        except ValueError:
            parser.error("Invalid start-time format. Use ISO format like '2024-01-01T00:00:00'")

    # Generate data
    print(f"Generating {args.observations} observations with {args.anomaly_rate:.1%} anomaly rate...")

    generator = DataGenerator(anomaly_rate=args.anomaly_rate, seed=args.seed)
    dataset = generator.generate_dataset(args.observations, start_time)

    # Save to file
    save_to_csv(dataset, args.output)

    # Print summary
    total_anomalies = int(args.observations * args.anomaly_rate)
    sensors_used = len(set(reading['sensor_id'] for reading in dataset))
    time_span = dataset[-1]['timestamp'][:10] if len(dataset) > 1 else "N/A"

    print(f"\nDataset summary:")
    print(f"  Total observations: {len(dataset)}")
    print(f"  Expected anomalies: ~{total_anomalies}")
    print(f"  Sensors included: {sensors_used}")
    print(f"  Time span: {time_span}")
    print(f"  Output file: {args.output}")

if __name__ == "__main__":
    main()
