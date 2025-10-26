# IoT Dashboard

This project is an IoT dashboard built with Streamlit for visualizing and analyzing data from IoT devices. It supports real-time data ingestion via MQTT and provides interactive charts, maps, and statistics for monitoring device metrics.

## Purpose

This dashboard is useful for people monitoring the flow height and other metrics on rivers and tracking their device locations. It helps predict upcoming floods and observe temperature changes to account for the migration of marine life.

## Features

- **Live MQTT Data**: Connects to an MQTT broker to receive real-time messages from IoT devices.
- **Data Visualization**:
  - Line charts for temperature, water level, and flow direction.
  - Interactive map showing the latest device locations.
- **Data Filtering**:
  - Filter by date range and device IDs.
  - Aggregate data by time intervals (e.g., 5 minutes, 1 hour).
- **Data Export**: Download processed data as a CSV file.
- **Auto-Refresh**: Pages auto-refresh at configurable intervals.

## Project Structure

- `app.py`: Main entry point for the Streamlit app, handling MQTT connection and live data display.
- `csv_store.py`: Handles CSV file operations for persisting data.
- `data_table.py`: Manages the in-memory data table and provides utility functions for data normalization and filtering.
- `mqtt.py`: Wrapper around the Paho MQTT client for connecting to the broker and subscribing to topics.
- `pages/02_Map.py`: Displays an interactive map with device locations.
- `pages/03_Stats.py`: Provides charts and statistics for device data.
- `.env`: Configuration file for MQTT broker credentials and settings.
- `ttn_messages.csv`: Stores historical IoT messages in CSV format.

## Requirements

- Python 3.9+
- Libraries:
  - `streamlit`
  - `pandas`
  - `numpy`
  - `altair`
  - `folium`
  - `streamlit-folium`
  - `paho-mqtt`
  - `python-dotenv`

Install dependencies using:
```bash
pip install -r requirements.txt
```

## Configuration

Set up the `.env` file with your MQTT broker details:
```plaintext
MQTT_HOST=your-mqtt-host
MQTT_PORT=8883
MQTT_USERNAME=your-username
MQTT_PASSWORD=your-password
MQTT_TOPIC=your-topic
```

## Usage

1. Start the Streamlit app:
   ```bash
   streamlit run app.py
   ```
2. Navigate to the provided URL in your browser.
3. Use the sidebar to configure filters, refresh intervals, and other options.

## Pages

- **MQTT Viewer**: Displays live messages and connection status.
- **Device Map**: Shows the latest device locations on an interactive map.
- **Device Statistics**: Provides charts and metrics for analyzing device data.

## Data Schema

The project uses the following schema for IoT messages:
- `ts`: Timestamp (ISO 8601 format, UTC).
- `device_id`: Unique identifier for the device.
- `water_temp_c`: Water temperature in °C.
- `water_level_mm`: Water level in millimeters.
- `flow_deg`: Flow direction in degrees.
- `latitude`: Latitude of the device.
- `longitude`: Longitude of the device.

## Scalability

To ensure our application can handle growth and increased demand, we have implemented the following scalability features:

- **Map Performance**:
  - Leveraged clustering for device markers to improve map rendering performance when dealing with a large number of devices.

- **Modular Architecture**:
  - Designed the application with a modular structure to facilitate the addition of new features and services without impacting existing functionality.

- **Asynchronous Processing**:
  - Integrated asynchronous data processing to ensure the application remains responsive under high loads.