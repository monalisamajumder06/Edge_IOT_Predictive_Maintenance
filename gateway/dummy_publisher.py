"""Python MQTT Dummy Telemetry Publisher for Edge Gateway Pipeline.

Subsystem: IoT + Backend + Dashboard (Member 3)
Phase: Phase 2 Baseline Development
Classification: [IMPLEMENTATION DECISION]

Provides two distinct operating modes:
1. NORMAL MODE:
   - Loads dummy predictions from data/dummy_predictions.json
   - Validates each payload strictly using CoreTelemetryPayload
   - Constructs topic: motors/{device_id}/prediction
   - Publishes valid telemetry with QoS 1
2. TEST / INVALID INJECTION MODE:
   - Deliberately bypasses CoreTelemetryPayload validation
   - Publishes malformed JSON, missing fields, invalid types, or topic mismatches
   - Enables end-to-end verification of Node-RED gateway error handling & rejection
"""

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

# Ensure project root is on sys.path for relative module imports
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from schemas.telemetry import CoreTelemetryPayload

# Configure structured logger
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("dummy_publisher")


def build_prediction_topic(device_id: str) -> str:
    """Build the MQTT prediction topic for a given device_id.
    
    Topic Convention: motors/{device_id}/prediction
    Classification: [IMPLEMENTATION DECISION]
    """
    return f"motors/{device_id}/prediction"


def load_dummy_dataset(file_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Load dummy predictions dataset from JSON file."""
    path = file_path or (PROJECT_ROOT / "data" / "dummy_predictions.json")
    if not path.exists():
        raise FileNotFoundError(f"Dummy predictions file not found at: {path}")

    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    if not isinstance(records, list):
        raise ValueError(f"Expected list of prediction records in {path}, got {type(records).__name__}")

    return records


def validate_and_format_payload(record: Dict[str, Any]) -> Tuple[str, str]:
    """Validate a telemetry record using CoreTelemetryPayload and format topic and JSON payload.
    
    Used in NORMAL mode.
    Returns:
        Tuple of (topic, json_payload_string)
    Raises:
        pydantic.ValidationError if record does not conform to CoreTelemetryPayload.
    """
    validated = CoreTelemetryPayload(**record)
    topic = build_prediction_topic(validated.device_id)
    # Exclude internal Pydantic fields, serialize core contract cleanly
    payload_str = validated.model_dump_json()
    return topic, payload_str


def generate_test_injection_payload(injection_type: str) -> Tuple[str, str]:
    """Generate invalid / malformed telemetry payloads for gateway rejection testing.
    
    Used in TEST mode. Bypasses CoreTelemetryPayload validation so invalid payloads
    can be transmitted to the broker and tested against the Node-RED gateway.
    
    Returns:
        Tuple of (topic, raw_payload_string)
    """
    if injection_type == "malformed-json":
        topic = build_prediction_topic("motor_01")
        # Broken JSON syntax (unclosed object and raw comma)
        payload_str = '{"device_id": "motor_01", "fault_type": "Inner_Race", MALFORMED_JSON'
        return topic, payload_str

    elif injection_type == "missing-field":
        topic = build_prediction_topic("motor_01")
        # Missing required field "health_index"
        payload_dict = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "rul_hours": 420,
        }
        return topic, json.dumps(payload_dict)

    elif injection_type == "invalid-type":
        topic = build_prediction_topic("motor_01")
        # "health_index" should be numeric float, here provided as invalid string
        payload_dict = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": "critical_failure_string",
            "rul_hours": 420,
        }
        return topic, json.dumps(payload_dict)

    elif injection_type == "topic-mismatch":
        # Payload says "motor_01", but topic specifies "motor_99"
        topic = build_prediction_topic("motor_99")
        payload_dict = {
            "device_id": "motor_01",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        return topic, json.dumps(payload_dict)

    elif injection_type == "empty-id":
        topic = "motors//prediction"
        payload_dict = {
            "device_id": "",
            "fault_type": "Inner_Race",
            "health_index": 0.88,
            "rul_hours": 420,
        }
        return topic, json.dumps(payload_dict)

    else:
        raise ValueError(
            f"Unknown injection_type: '{injection_type}'. "
            "Supported types: 'malformed-json', 'missing-field', 'invalid-type', 'topic-mismatch', 'empty-id'."
        )


class MqttDummyPublisher:
    """MQTT client wrapper for publishing telemetry to Mosquitto broker."""

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        keepalive: Optional[int] = None,
        client_id: Optional[str] = None,
        qos: int = 1,
    ):
        settings = get_settings()
        self.host = host or settings.mqtt_broker_host
        self.port = port or settings.mqtt_broker_port
        self.keepalive = keepalive or settings.mqtt_keepalive
        self.client_id = client_id or f"dummy_publisher_{int(time.time())}"
        self.qos = qos
        self.connected = False

        # Initialize paho-mqtt client with modern v2 API callback convention
        self.client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.client_id,
            protocol=mqtt.MQTTv5,
        )
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_publish = self._on_publish

    def _on_connect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        if reason_code == 0 or (hasattr(reason_code, "is_failure") and not reason_code.is_failure):
            self.connected = True
            logger.info("Connected to MQTT broker at %s:%d (client_id=%s)", self.host, self.port, self.client_id)
        else:
            self.connected = False
            logger.error("Failed to connect to MQTT broker: reason_code=%s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        self.connected = False
        logger.info("Disconnected from MQTT broker (reason_code=%s)", reason_code)

    def _on_publish(self, client: mqtt.Client, userdata: Any, mid: int, reason_code: Any = None, properties: Any = None) -> None:
        logger.debug("Message delivered to broker (mid=%d)", mid)

    def connect(self) -> bool:
        """Connect to the configured MQTT broker with error handling."""
        try:
            logger.info("Connecting to Mosquitto broker at %s:%d...", self.host, self.port)
            self.client.connect(self.host, self.port, keepalive=self.keepalive)
            self.client.loop_start()

            # Wait briefly for connection handshake to complete
            start = time.time()
            while not self.connected and (time.time() - start) < 3.0:
                time.sleep(0.05)

            if not self.connected:
                logger.warning("Broker handshake timed out after 3 seconds; will attempt operation anyway.")
            return self.connected
        except ConnectionRefusedError as exc:
            logger.error("Connection refused by broker at %s:%d. Is Mosquitto running? (%s)", self.host, self.port, exc)
            return False
        except Exception as exc:
            logger.error("Unexpected error connecting to broker %s:%d: %s", self.host, self.port, exc)
            return False

    def publish_message(self, topic: str, payload_str: str) -> bool:
        """Publish payload to topic with QoS 1 and log result."""
        try:
            info = self.client.publish(topic, payload=payload_str, qos=self.qos, retain=False)
            info.wait_for_publish(timeout=3.0)
            if info.is_published():
                logger.info("[PUBLISH SUCCESS] Topic: %s | Payload: %s", topic, payload_str)
                return True
            else:
                logger.warning("[PUBLISH PENDING/TIMEOUT] Topic: %s (mid=%d)", topic, info.mid)
                return False
        except Exception as exc:
            logger.error("[PUBLISH ERROR] Failed publishing to topic %s: %s", topic, exc)
            return False

    def disconnect(self) -> None:
        """Disconnect and stop client loop cleanly."""
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass


def run_normal_mode(
    publisher: MqttDummyPublisher,
    dataset_path: Optional[Path] = None,
    once: bool = True,
    delay_seconds: float = 1.0,
) -> int:
    """Run publisher in NORMAL mode: validate with schema, then publish."""
    logger.info("--- Starting NORMAL Mode: Validating against CoreTelemetryPayload ---")
    records = load_dummy_dataset(dataset_path)
    logger.info("Loaded %d records from dummy dataset.", len(records))

    published_count = 0
    try:
        while True:
            for idx, record in enumerate(records, start=1):
                try:
                    topic, payload_str = validate_and_format_payload(record)
                    logger.info("[Record %d/%d] CoreTelemetryPayload validation PASSED.", idx, len(records))
                    success = publisher.publish_message(topic, payload_str)
                    if success:
                        published_count += 1
                except Exception as exc:
                    logger.error("[Record %d/%d] Validation FAILED on publisher side: %s", idx, len(records), exc)

                if len(records) > 1 and delay_seconds > 0:
                    time.sleep(delay_seconds)

            if once:
                break
            time.sleep(delay_seconds)

    except KeyboardInterrupt:
        logger.info("Publisher stopped by user.")

    logger.info("NORMAL Mode finished. Total valid messages published: %d", published_count)
    return published_count


def run_test_mode(
    publisher: MqttDummyPublisher,
    injection_type: str,
) -> bool:
    """Run publisher in TEST INJECTION mode: bypass schema and publish invalid payload."""
    logger.info("--- Starting TEST Mode: Injecting '%s' (CoreTelemetry validation BYPASSED) ---", injection_type)
    topic, raw_payload = generate_test_injection_payload(injection_type)
    logger.info("Generated raw test payload: topic='%s', content='%s'", topic, raw_payload)
    success = publisher.publish_message(topic, raw_payload)
    logger.info("TEST Mode finished. Injected payload published: %s", success)
    return success


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Edge-IoT Dummy MQTT Publisher for Raspberry Pi Gateway Ingestion Pipeline."
    )
    parser.add_argument(
        "--mode",
        choices=["normal", "test"],
        default="normal",
        help="Operating mode: 'normal' validates with schema; 'test' injects invalid messages bypassing schema.",
    )
    parser.add_argument(
        "--inject",
        choices=["malformed-json", "missing-field", "invalid-type", "topic-mismatch", "empty-id"],
        default="malformed-json",
        help="Type of invalid payload to inject when --mode is 'test'.",
    )
    parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="MQTT broker hostname/IP (default: from config/settings.py).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="MQTT broker port (default: from config/settings.py).",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        default=True,
        help="Publish the dataset once and exit (default: True).",
    )
    parser.add_argument(
        "--loop",
        dest="once",
        action="store_false",
        help="Continuously loop through dummy dataset.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=1.0,
        help="Delay in seconds between records in loop (default: 1.0s).",
    )

    args = parser.parse_args()

    publisher = MqttDummyPublisher(host=args.host, port=args.port)
    if not publisher.connect():
        logger.error("Could not connect to MQTT broker. Exiting.")
        sys.exit(1)

    try:
        if args.mode == "normal":
            count = run_normal_mode(publisher, once=args.once, delay_seconds=args.delay)
            if count == 0:
                sys.exit(1)
        elif args.mode == "test":
            success = run_test_mode(publisher, injection_type=args.inject)
            if not success:
                sys.exit(1)
    finally:
        publisher.disconnect()


if __name__ == "__main__":
    main()
