# Raspberry Pi Gateway & Node-RED Routing Subsystem
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Phase: Phase 2 Implementation Baseline

This directory contains the edge gateway software configuration, publisher testing tools, and Node-RED ingestion flows for the **Raspberry Pi 4 Gateway**.

---

## 1. Subsystem Architecture & Responsibilities

In Phase 2, Member 3 delivers the software-only edge gateway ingestion pipeline:

```
                               ┌──────────────────────────────────────────────┐
                               │       [PYTHON DUMMY PUBLISHER]               │
                               │             gateway/dummy_publisher.py       │
                               │                                              │
                               │  [NORMAL MODE]        [TEST INJECTION MODE]  │
                               │  - Read dummy data    - Corrupt JSON syntax  │
                               │  - Validate with      - Missing fields       │
                               │    CoreTelemetry       - Wrong types          │
                               │  - Build topic        - Topic/ID mismatch    │
                               │  - Publish valid      - Bypasses schema      │
                               └──────────────┬───────────────────────────────┘
                                              │ TCP / MQTT Port 1883 (QoS 1)
                                              ▼
                               ┌──────────────────────────────────────────────┐
                               │           [MOSQUITTO BROKER 2.1.2]           │
                               │            gateway/mosquitto/                │
                               │              mosquitto.conf                  │
                               │  - Port 1883, allow_anonymous true           │
                               │  - MQTT 5.0 & 3.1.1 compatible               │
                               │  - Routes motors/{device_id}/prediction      │
                               └──────────────┬───────────────────────────────┘
                                              │ Subscription: motors/+/prediction
                                              ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                       [NODE-RED GATEWAY FLOW]                               │
│                      gateway/flows/gateway_flow.json                        │
│                                                                             │
│  1. MQTT In Node (`motors/+/prediction`, QoS 1)                             │
│     ↓                                                                       │
│  2. Safe JSON Parser Node (catches malformed syntax safely)                 │
│     ↓                                                                       │
│  3. Function Node: Telemetry & Topic Validation                             │
│     - Verify 4 required fields present & non-empty                          │
│     - Verify numeric types (health_index, rul_hours)                        │
│     - Verify device_id matches topic wildcard token                         │
│     - Ingest timestamp fallback (ISO-8601 UTC if omitted)                   │
│     ↓                                                                       │
│  4. Bifurcated Output Routing:                                              │
│     ├── Output 1 (Valid): Normalized Gateway Output → [GATEWAY ACCEPTED]    │
│     └── Output 2 (Invalid): Structured Rejection Log → [GATEWAY REJECTED]   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Directory Layout

```
gateway/
├── README.md                      # This comprehensive guide
├── dummy_publisher.py             # Python MQTT publisher (Normal & Test modes)
├── mosquitto/
│   └── mosquitto.conf             # Portable Mosquitto broker configuration
└── flows/
    └── gateway_flow.json          # Complete Node-RED gateway ingestion flow
```

---

## 3. MQTT Broker (Mosquitto 2.1.2) Setup & Operation

The broker accepts telemetry from motor edge devices and forwards them to the Node-RED gateway.

### Broker Specification
- **Default Port**: `1883`
- **Supported Protocols**: MQTT 5.0 and MQTT 3.1.1
- **Authentication**: `allow_anonymous true` for local development and Phase 2 testing.
- **Config File**: `gateway/mosquitto/mosquitto.conf`

### Windows Operations

#### Option A: Running as a Windows Service (Installed)
Mosquitto can run as a background service:
```powershell
# Check service status
Get-Service mosquitto

# Start service
Start-Service mosquitto

# Stop service
Stop-Service mosquitto
```

#### Option B: Running from Command Line
To run Mosquitto directly in the foreground using the project configuration:
```powershell
& "C:\Program Files\mosquitto\mosquitto.exe" -c gateway\mosquitto\mosquitto.conf -v
```

#### Verifying Broker Is Listening
```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 1883
```

---

### Raspberry Pi 4 (Linux) Operations

> [!NOTE]
> These instructions are structured for Raspberry Pi OS (64-bit Debian Bookworm). Actual hardware verification will take place when code is deployed onto physical Raspberry Pi hardware.

#### 1. Install Mosquitto
```bash
sudo apt update
sudo apt install -y mosquitto mosquitto-clients
```

#### 2. Deploy Configuration
```bash
sudo cp gateway/mosquitto/mosquitto.conf /etc/mosquitto/conf.d/gateway.conf
```

#### 3. Service Management
```bash
# Enable Mosquitto on boot
sudo systemctl enable mosquitto

# Start / Restart broker
sudo systemctl restart mosquitto

# Check status
sudo systemctl status mosquitto
```

#### 4. Verify on Raspberry Pi
```bash
mosquitto_sub -t "motors/+/prediction" -v
```

---

## 4. Python MQTT Dummy Publisher (`gateway/dummy_publisher.py`)

A modular testing client simulating the future edge MCU inference publisher.

### Design Principles
1. **Configurable**: Loads host, port, keepalive from `config/settings.py` (overridable via `--host`, `--port`).
2. **Normal Mode**: Validates every payload strictly against `schemas.telemetry.CoreTelemetryPayload` before transmission. Only valid records are published.
3. **Test Injection Mode**: Intentionally **bypasses** `CoreTelemetryPayload` validation to transmit malformed/corrupt payloads directly to the broker, enabling verification of Node-RED rejection logic.

### Usage Commands

#### Normal Mode (Schema-Validated)
```powershell
# Publish the dummy dataset once (all 3 records)
python gateway/dummy_publisher.py --mode normal --once

# Continuous publishing in a loop with 2.0s delay
python gateway/dummy_publisher.py --mode normal --loop --delay 2.0

# Target a remote broker (e.g. Raspberry Pi)
python gateway/dummy_publisher.py --mode normal --host 192.168.1.50 --port 1883
```

#### Test / Invalid Injection Mode (Bypasses Schema)
```powershell
# 1. Malformed JSON syntax (unclosed brackets / invalid syntax)
python gateway/dummy_publisher.py --mode test --inject malformed-json

# 2. Missing required field (missing health_index)
python gateway/dummy_publisher.py --mode test --inject missing-field

# 3. Invalid field type (string passed for numeric health_index)
python gateway/dummy_publisher.py --mode test --inject invalid-type

# 4. Topic mismatch (payload has motor_01, topic has motor_99)
python gateway/dummy_publisher.py --mode test --inject topic-mismatch

# 5. Empty device_id string
python gateway/dummy_publisher.py --mode test --inject empty-id
```

---

## 5. Node-RED Gateway Flow (`gateway/flows/gateway_flow.json`)

### Flow Structure
1. **MQTT In**: Subscribes to wildcard pattern `motors/+/prediction` at QoS 1 on `localhost:1883`.
2. **JSON Parser**: Converts raw MQTT UTF-8 string to JavaScript object.
3. **Catch Node**: Traps malformed JSON parsing errors, preventing the flow from crashing, and formats a structured rejection message.
4. **Validate & Normalize Function Node**:
   - Validates topic conforms to `motors/{device_id}/prediction`.
   - Validates payload is an object.
   - Validates 4 required core fields: `device_id`, `fault_type`, `health_index`, `rul_hours`.
   - Validates field types: `health_index` is numeric float, `rul_hours` is numeric.
   - Validates that `device_id` inside payload strictly matches the `{device_id}` token in the topic.
   - Attaches arrival UTC timestamp if `timestamp` is omitted (fallback recommendation).
   - Bifurcates output: Output 1 for Accepted, Output 2 for Rejected.
5. **Debug Loggers**:
   - `[GATEWAY ACCEPTED]`: Displays normalized JSON ready for downstream storage.
   - `[GATEWAY REJECTED]`: Displays rejected payload with exact error reason.

### Running Node-RED

#### Windows Development Run
```powershell
# Start Node-RED with project flow
node-red gateway/flows/gateway_flow.json
```
Access the Node-RED web interface at `http://127.0.0.1:1880/`.

#### Raspberry Pi 4 Run
```bash
# Install Node-RED via official script
bash <(curl -sL https://raw.githubusercontent.com/node-red/linux-installers/master/deb/update-nodejs-and-nodered)

# Start as systemd service
sudo systemctl enable nodered.service
sudo systemctl start nodered.service
```

---

## 6. Gateway Validation & Error Handling Matrix

| Scenario | Gateway Action | Disposition | Forward Downstream | Handling Description |
| :--- | :--- | :--- | :--- | :--- |
| **Valid Telemetry** | Accepted | `ACCEPTED` | Yes (Output 1) | Meets all contract requirements; fallback UTC timestamp attached if missing. |
| **Malformed JSON** | Rejected | `REJECTED` | No (Output 2) | Caught by Catch node; flow does not crash; error reason logged. |
| **Missing Required Field** | Rejected | `REJECTED` | No (Output 2) | Missing `device_id`, `fault_type`, `health_index`, or `rul_hours`; rejected & logged. |
| **Invalid Field Type** | Rejected | `REJECTED` | No (Output 2) | Non-numeric `health_index` or `rul_hours`; rejected & logged. |
| **Topic / Payload ID Mismatch** | Rejected | `REJECTED` | No (Output 2) | Sensor ID in payload differs from MQTT topic; rejected to prevent misrouting. |
| **Unknown Device ID** | Accepted | `ACCEPTED` | Yes (Output 1) | Dynamic motor discovery is permitted; contract allows any non-empty string ID. |
| **Duplicate Messages** | Accepted | `ACCEPTED` | Yes (Output 1) | **Gateway does not perform deduplication**; messages pass through. Idempotency is deferred to Phase 3 (persistence layer). |
| **Concurrent Multi-Device Telemetry** | Accepted | `ACCEPTED` | Yes (Output 1) | Processed asynchronously by Node-RED through wildcard `motors/+/prediction`. |
| **MQTT Broker Unavailable** | Publisher retries | `ERROR` | N/A | MQTT client reconnects automatically; gateway resumes when broker is available. |

---

## 7. Buffering Design Boundary

- **Phase 2 Boundary**:
  - Telemetry messages are processed strictly **in-flight** through Node-RED.
  - **No persistent gateway disk buffer or local database queue is implemented in Phase 2**.
  - Persistent buffering and backpressure handling (e.g. disk-backed queueing when InfluxDB is unreachable) are explicitly deferred to **Phase 3** when InfluxDB is introduced.
  - MQTT QoS 1 is maintained between edge publisher and broker for transport acknowledgment, but is not treated as a substitute for persistent storage buffering.

---

## 8. Step-by-Step Local Demonstration

To execute the complete end-to-end local demonstration:

### Step 1: Verify Mosquitto Broker Is Running
```powershell
Test-NetConnection -ComputerName 127.0.0.1 -Port 1883
```
*Expected*: `TcpTestSucceeded : True`

### Step 2: Start Node-RED
In a separate terminal:
```powershell
node-red gateway/flows/gateway_flow.json
```
*Expected*: Node-RED starts and displays:
`[info] [mqtt-broker:Mosquitto Local Broker] Connected to broker: nodered_gateway_listener@mqtt://localhost:1883`

### Step 3: Run Dummy Publisher (Normal Mode)
In a primary terminal:
```powershell
python gateway/dummy_publisher.py --mode normal --once
```
*Expected Output in Node-RED Terminal*:
```json
[debug:[GATEWAY ACCEPTED]]
{
  status: 'ACCEPTED',
  disposition: 'ACCEPTED',
  device_id: 'motor_01',
  fault_type: 'Inner_Race',
  health_index: 0.88,
  rul_hours: 420,
  timestamp: '2026-09-13T10:43:55.000Z',
  gateway_received_at: '2026-09-13T10:43:55.000Z',
  topic: 'motors/motor_01/prediction'
}
```

### Step 4: Run Dummy Publisher (Invalid Injection Test)
```powershell
python gateway/dummy_publisher.py --mode test --inject malformed-json
python gateway/dummy_publisher.py --mode test --inject missing-field
python gateway/dummy_publisher.py --mode test --inject invalid-type
python gateway/dummy_publisher.py --mode test --inject topic-mismatch
```
*Expected Output in Node-RED Terminal*:
```json
[debug:[GATEWAY REJECTED]]
{
  status: 'REJECTED',
  disposition: 'REJECTED',
  reason: 'Malformed JSON syntax - payload cannot be parsed',
  ...
}
```
All invalid messages are safely rejected and logged without stopping or crashing Node-RED.

---

## 9. Automated Testing

To run the automated contract and publisher unit test suite:
```powershell
python -m pytest tests/ -v
```
All 34 unit tests should pass.
