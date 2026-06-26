"""
Smart Solar Plug — MQTT Listener
Runs as a background thread. Subscribes to an MQTT topic for telemetry.
On new data: persists to SQLite, runs ML inference, stores alerts, broadcasts via WebSocket.
"""

import os
import json
import threading
from typing import Optional

import paho.mqtt.client as mqtt
from telemetry_processor import process_telemetry

_mqtt_client: Optional[mqtt.Client] = None
_db_session_factory = None
_ml_predict_cleaning = None
_ml_predict_degradation = None

def _on_connect(client, userdata, flags, rc):
    if rc == 0:
        topic = os.getenv("MQTT_TOPIC", "solar/telemetry")
        print(f"[MQTT] Connected successfully. Subscribing to {topic} ...")
        client.subscribe(topic)
    else:
        print(f"[MQTT] Connection failed with code {rc}")

def _on_message(client, userdata, msg):
    try:
        payload = msg.payload.decode("utf-8")
        data = json.loads(payload)
        
        if _db_session_factory and _ml_predict_cleaning and _ml_predict_degradation:
            process_telemetry(
                data,
                _db_session_factory,
                _ml_predict_cleaning,
                _ml_predict_degradation
            )
    except json.JSONDecodeError:
        print("[MQTT] Received non-JSON payload, ignoring.")
    except Exception as e:
        print(f"[MQTT] Message process error: {e}")

def start_mqtt_listener(db_session_factory, ml_predict_cleaning, ml_predict_degradation):
    """Start the MQTT listener in a background thread."""
    global _mqtt_client, _db_session_factory, _ml_predict_cleaning, _ml_predict_degradation
    
    _db_session_factory = db_session_factory
    _ml_predict_cleaning = ml_predict_cleaning
    _ml_predict_degradation = ml_predict_degradation

    broker = os.getenv("MQTT_BROKER", "localhost")
    port = int(os.getenv("MQTT_PORT", 1883))
    username = os.getenv("MQTT_USERNAME", "")
    password = os.getenv("MQTT_PASSWORD", "")

    _mqtt_client = mqtt.Client()

    if username:
        _mqtt_client.username_pw_set(username, password)

    _mqtt_client.on_connect = _on_connect
    _mqtt_client.on_message = _on_message

    try:
        _mqtt_client.connect(broker, port, 60)
        _mqtt_client.loop_start()
        print(f"[MQTT] Background listener thread started. Connecting to {broker}:{port}...")
    except Exception as e:
        print(f"[MQTT] Failed to start MQTT client: {e}")

def stop_mqtt_listener():
    """Stop the MQTT listener thread."""
    global _mqtt_client
    if _mqtt_client:
        _mqtt_client.loop_stop()
        _mqtt_client.disconnect()
        print("[MQTT] Listener thread stopped.")
