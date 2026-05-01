# Data Generator Usage Guide

The `generate_data.py` script creates realistic sensor time-series data with controllable anomalies for testing your pipeline.

## Quick Start

```bash
# Generate 1000 observations (default)
python3 generate_data.py

# Generate 50,000 observations for performance testing  
python3 generate_data.py -n 50000 -o large_dataset.csv

# Generate data with higher anomaly rate (10%)
python3 generate_data.py -n 5000 --anomaly-rate 0.1

# Reproducible data generation with seed
python3 generate_data.py -n 1000 --seed 42
```

## Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--observations` | `-n` | 1000 | Number of sensor readings to generate |
| `--output` | `-o` | `sample_data.csv` | Output CSV filename |
| `--anomaly-rate` | | 0.03 | Fraction of anomalous readings (0.0-1.0) |
| `--seed` | | None | Random seed for reproducible data |
| `--start-time` | | 24h ago | Starting timestamp (ISO format) |

## Generated Data Format

The script creates CSV files with these columns:
- `id`: Unique reading identifier
- `timestamp`: ISO 8601 timestamp with timezone
- `sensor_id`: Sensor identifier (TEMP_001, HUMID_003, etc.)
- `temperature`: Temperature in Celsius
- `humidity`: Relative humidity (0-100%)
- `pressure`: Atmospheric pressure in hPa
- `location`: Sensor physical location

## Sensor Types

The generator includes 5 different sensors:
- **TEMP_001** (lab_a): Laboratory temperature sensor
- **TEMP_002** (lab_b): Secondary lab sensor  
- **HUMID_003** (greenhouse): High-humidity environment
- **PRESS_004** (outdoor): Weather monitoring
- **MULTI_005** (server_room): IT infrastructure monitoring

## Anomaly Types

The script injects realistic anomalies:
- **Spikes**: Sudden high/low readings
- **Sensor Failures**: Readings stuck at error values (-999, 0)
- **Drift**: Gradual increase/decrease over time
- **Noise Bursts**: High-frequency measurement errors

## Testing Different Scenarios

```bash
# Small dataset for development
python3 generate_data.py -n 100 --anomaly-rate 0.1

# Medium dataset for integration testing
python3 generate_data.py -n 5000 --anomaly-rate 0.05

# Large dataset for performance testing (>10k requirement)
python3 generate_data.py -n 25000 --anomaly-rate 0.03

# Stress test with many anomalies
python3 generate_data.py -n 10000 --anomaly-rate 0.15
```

With slight modification, the `anomaly_detector.py` script should work seamlessly with the generated data.
