# MQTT Topic & Messaging Architecture
## Subsystem: IoT + Backend + Dashboard

---

## 1. Topic Hierarchy Design `[IMPLEMENTATION DECISION]`

The MQTT topic convention is designed to be clear, predictable, and horizontally scalable from a single motor bench setup to a multi-motor industrial plant floor without changing routing code.

### Base Pattern
```
motors/{device_id}/{telemetry_type}
```

* `motors`: Root namespace designating industrial motor assets.
* `{device_id}`: Unique identifier of the motor asset (e.g., `motor_01`, `motor_02`).
* `{telemetry_type}`: The classification of message emitted (`prediction`, `status`).

---

## 2. Topic Specification Table

| Topic Pattern | Publisher | Subscriber | Payload Format | QoS | Retained | Purpose & Description | Classification |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `motors/{device_id}/prediction` | Dummy Generator (Phase 1) / ESP32-S3 / STM32H7 (Phase 2+) | Raspberry Pi Gateway / Node-RED / Backend Subscriber | Telemetry JSON Contract (`device_id`, `fault_type`, `health_index`, `rul_hours`) | **1** (At least once) | **No** (`false`) | Periodic inference results emitted after each DSP window (e.g. 1-second interval). QoS 1 ensures critical degradation telemetry is not dropped over lossy industrial wireless. | `[RECOMMENDATION]` |
| `motors/{device_id}/status` | Edge MCU or Gateway Agent | Gateway / Backend Monitor / Dashboard | Status JSON (e.g. `{"device_id": "motor_01", "state": "ONLINE"}`) | **1** (At least once) | **Yes** (`true`) | Device liveness, heartbeat, and connection state. Retained flag enables new dashboard sessions to immediately see current motor online state. | `[RECOMMENDATION]` |
| `motors/+/prediction` | Wildcard Pattern | Node-RED / InfluxDB Collector | Telemetry JSON | **1** | N/A | Subscribed by the ingestion pipeline to capture predictions across all motors simultaneously using single-level wildcard `+`. | `[IMPLEMENTATION DECISION]` |

---

## 3. Design Rationale

### 3.1 Why Not Over-Engineer?
Industrial IoT designs sometimes create excessively deep topic paths (e.g., `company/site/building/line/motor/component/subcomponent/data`). 
For this project:
- The edge MCU runs on constrained resources (lwIP / embedded MQTT clients). Simple topic formatting reduces RAM allocation and string parsing overhead on the MCU.
- `motors/{device_id}/prediction` provides clean isolation while allowing Node-RED or Python subscribers to capture all motors using `motors/+/prediction`.

### 3.2 QoS (Quality of Service) Decision
* **QoS 0 (At most once)**: High throughput, but risk of silent message loss during network congestion. Not acceptable for predictive maintenance alerts.
* **QoS 1 (At least once) - SELECTED**: Ensures every prediction payload is acknowledged by the Mosquitto broker. Downstream database writes are naturally idempotent when using indexed timestamps.
* **QoS 2 (Exactly once)**: Adds 4-step handshake overhead, unnecessary for 1-second interval streaming telemetry.

### 3.3 Message Retention Decision
* **Telemetry (`motors/{device_id}/prediction`)**: `retained = false`. Stale telemetry should not be pushed to a newly connected subscriber; only live streaming inferences belong here.
* **Status (`motors/{device_id}/status`)**: `retained = true`. Guarantees immediate visibility of whether a motor MCU is connected or offline (via MQTT Last Will and Testament - LWT).

---

## 4. Hardware Replacement Compatibility

When the project transitions from Phase 1 dummy telemetry to real hardware:
1. The ESP32-S3 or STM32H7 firmware will configure its MQTT client to connect to Mosquitto (port 1883).
2. It publishes to the identical topic: `motors/motor_01/prediction`.
3. The gateway, database, and backend will receive and process the payload with **zero reconfiguration or code modification**.
