# InfluxDB Time-Series Storage Architecture & Schema Specification
## Subsystem: IoT + Backend + Dashboard (Member 3)
### Phase: Phase 3 Implementation Baseline

---

## 1. Subsystem Architecture Overview `[PROJECT REQUIREMENT]`

In Phase 3, Member 3 establishes the persistent time-series database layer:

```
┌─────────────────────────────────────────────────────────────┐
│ [TEST PRODUCER]                                             │
│ Python Dummy Telemetry Publisher (Normal & Test Modes)      │
│ - Publishes contract JSON to `motors/{device_id}/prediction`│
└──────────────────────────────┬──────────────────────────────┘
                               │ MQTT (QoS 1)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [MQTT BROKER]                                               │
│ Mosquitto Broker (Port 1883)                                │
│ - Dispatches messages for `motors/+/prediction`             │
└──────────────────────────────┬──────────────────────────────┘
                               │ MQTT Ingest
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [GATEWAY LAYER] (Phase 2 Baseline + Phase 3 Extension)      │
│ Node-RED Ingestion Pipeline                                 │
│ 1. MQTT In Node (`motors/+/prediction`, QoS 1)              │
│ 2. Safe JSON Parse & Catch (traps malformed JSON syntax)    │
│ 3. Validation & Normalization (verifies 4 core fields,      │
│    types, and topic matching; attaches arrival timestamp)   │
│ 4. Rejection Path -> [GATEWAY REJECTED] Debug Log           │
│ 5. Acceptance Path -> Output 1: Normalized Telemetry        │
│ 6. Transform to Line Protocol (env.get() dynamic config)    │
│ 7. HTTP Request Node -> InfluxDB v2 `/api/v2/write`         │
│ 8. Response Check & Scoped Catch (Status 204 or Outage)     │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP POST /api/v2/write (Line Protocol)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [PERSISTENCE LAYER] `[PROJECT REQUIREMENT]`                 │
│ InfluxDB v2 Time-Series Database                            │
│ - Bucket: `motor_telemetry` `[IMPLEMENTATION DECISION]`     │
│ - Measurement: `predictions` `[IMPLEMENTATION DECISION]`     │
│ - Tag: `device_id` `[IMPLEMENTATION DECISION]`              │
│ - Fields: `fault_type`, `health_index`, `rul_hours`         │
└──────────────────────────────┬──────────────────────────────┘
                               │ Flux Queries (Phase 4 Preparation)
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [APPLICATION API LAYER] `[FUTURE WORK - Phase 4]`           │
│ FastAPI Backend Service (Out of Scope for Phase 3)          │
└──────────────────────────────┬──────────────────────────────┘
                               │ HTTP / WebSocket REST JSON
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ [PRESENTATION LAYER] `[FUTURE WORK - Phase 5]`              │
│ Dashboard (Streamlit / Grafana)                             │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Storage Schema & Line Protocol Specification

### 2.1 Measurement Design `[IMPLEMENTATION DECISION]`
* **Measurement Name**: `predictions`
* *Rationale*: Represents model prediction events emitted per motor analysis window, matching Phase 1 architectural definitions.

### 2.2 Tag Set `[IMPLEMENTATION DECISION]`
| Tag Key | Data Type | Example | Indexing | Purpose & Design Rationale |
| :--- | :--- | :--- | :--- | :--- |
| `device_id` | `string` | `"motor_01"` | **Indexed** | Primary identifier for the physical motor asset. InfluxDB indexes tags in memory (TSI), enabling instantaneous filtering by motor (e.g. `r.device_id == "motor_01"`). Distinct tag values create separate series, preventing data collision across multiple motors. |

### 2.3 Field Set `[IMPLEMENTATION DECISION]`
| Field Key | InfluxDB Type | Telemetry Source | Example | Purpose & Design Rationale |
| :--- | :--- | :--- | :--- | :--- |
| `fault_type` | `string` | `fault_type` | `"Inner_Race"` | Diagnostic classification label. Stored as string field rather than a tag to prevent high tag-cardinality growth as new fault categories or compound labels are evaluated. |
| `health_index` | `float` | `health_index` | `0.88` | Continuous degradation index. Stored as float to support numerical aggregation functions (mean, min, derivatives). |
| `rul_hours` | `float` | `rul_hours` | `420.0` | Remaining Useful Life in operating hours. Coerced to float in InfluxDB to prevent schema conflicts across integer/float emissions from ML models. |

### 2.4 Timestamp Semantics `[IMPLEMENTATION DECISION / OPEN DECISION]`
* **Timestamp Resolution**: Millisecond Unix epoch integer (`precision=ms`).
* **Origin & Ingestion Semantics**:
  - Phase 3 consumes the normalized timestamp already attached in Phase 2 Output 1.
  - If upstream edge telemetry includes an ISO-8601 timestamp, it is converted to millisecond epoch and preserved.
  - If omitted by the edge device, Phase 2 gateway arrival UTC timestamp is used.
  - *Status*: Hardware edge timestamp ownership remains an `[OPEN DECISION]` pending coordination with Member 1 & Member 2; Phase 3 makes no speculative assumptions.

### 2.5 Line Protocol Syntax Example
```text
predictions,device_id=motor_01 fault_type="Inner_Race",health_index=0.88,rul_hours=420.0 1789297302880
```
- **Escaping Rules Handled**:
  - Tags: Commas (`,`), spaces (` `), and equals (`=`) escaped with `\`.
  - String Fields: Wrapped in double quotes (`""`), internal quotes and backslashes escaped.
  - Numeric Fields: Formatted without quotes (`0.88`, `420.0`).

---

## 3. Node-RED Gateway Ingestion & Persistence Pipeline

The Phase 2 Node-RED flow (`gateway/flows/gateway_flow.json`) has been extended with the database write stage:

```
[MQTT In: motors/+/prediction]
          │
          ▼
[JSON Parser: Parse JSON] ───(parse error)───> [Format Parse Rejection] ───> [GATEWAY REJECTED]
          │
          ▼
[Validate & Normalize Telemetry]
     │                       │
     │ (Output 2: Invalid)   └─ (Output 1: Valid)
     ▼                                    │
[GATEWAY REJECTED]                        ├───────────────────────────────────┐
                                          ▼                                   ▼
                             [Transform to Line Protocol]           [GATEWAY ACCEPTED]
                                          │
                                          ▼
                             [HTTP Request: Write InfluxDB] ──(catch error)──> [Handle InfluxDB Outage]
                                          │                                            │
                                          ▼                                            ▼
                             [Check HTTP Status 204]                        [INFLUXDB UNAVAILABLE]
                              │                   │
                        (204 Success)       (!= 204 Error)
                              │                   │
                              ▼                   ▼
                     [INFLUXDB SUCCESS]   [INFLUXDB WRITE FAILED]
```

### 3.1 Dynamic Configuration via `env.get()` `[IMPLEMENTATION DECISION]`
To avoid hardcoding endpoints and credentials, the `Transform to Line Protocol` function node dynamically queries Node-RED environment variables:
```javascript
const influxUrl = (env.get("INFLUXDB_URL") || "http://localhost:8086").replace(/\/+$/, "");
const influxOrg = env.get("INFLUXDB_ORG") || "industrial_iot";
const influxBucket = env.get("INFLUXDB_BUCKET") || "motor_telemetry";
const influxToken = env.get("INFLUXDB_TOKEN") || "my-secure-placeholder-token";

msg.url = `${influxUrl}/api/v2/write?org=${encodeURIComponent(influxOrg)}&bucket=${encodeURIComponent(influxBucket)}&precision=ms`;
msg.headers = {
    "Authorization": `Token ${influxToken}`,
    "Content-Type": "text/plain; charset=utf-8"
};
msg.method = "POST";
msg.payload = lineProtocol;
```

---

## 4. Error Handling & Database Outages `[IMPLEMENTATION DECISION]`

1. **Database Outage / Network Disconnection**:
   - The HTTP Request node is wrapped with a scoped Node-RED `catch` node (`catch_influxdb_network_error`).
   - If InfluxDB is stopped, restarting, or network is unreachable, the catch node intercepts the error without crashing the Node-RED process.
   - The event is formatted with failure diagnostics and routed to `[INFLUXDB UNAVAILABLE]`.
2. **Invalid Database Responses (e.g. 401 Unauthorized, 404 Bucket Not Found)**:
   - Evaluated by `Check InfluxDB Response` function node.
   - Non-204 status codes are routed to Output 2 and logged to `[INFLUXDB WRITE FAILED]` with response body.
3. **Malformed Ingest Telemetry**:
   - Filtered out during Phase 2 validation at `func_validate_and_normalize`.
   - Never forwarded to the Line Protocol formatter or InfluxDB write node.
4. **Buffering Boundary `[RECOMMENDATION / FUTURE WORK]`**:
   - In-memory failure logging is active.
   - Persistent disk-backed queueing (e.g., SQLite buffer) is deferred as future work to keep Phase 3 lean and robust.

---

## 5. Multi-Motor Support `[IMPLEMENTATION DECISION]`

Multiple motors (`motor_01`, `motor_02`, `motor_03`) coexist in the same InfluxDB deployment:
- Telemetry from each motor writes with `device_id=<motor_id>` tag.
- InfluxDB stores them in independent time series.
- Writing data for `motor_02` at the exact same timestamp as `motor_01` does not cause overwrites or key collisions.

---

## 6. Multi-Label Fault Representation `[OPEN DECISION]`

- **Status**: Motor fault classification is conceptually multi-label, but the exact edge serialization structure remains an `[OPEN DECISION]` with Member 2.
- **Current Approach**: `fault_type` is stored as a string field (e.g. `"Inner_Race"`).
- **Future Coordination**: If Member 2 provides an array of faults (e.g. `["Inner_Race", "Overheating"]`) or probability maps, the Line Protocol serializer will serialize compound fault tags or auxiliary probability fields without breaking existing time-series continuity.

---

## 7. Preparation for Future FastAPI Backend `[FUTURE WORK / Phase 4 Preparation]`

> [!NOTE]
> FastAPI routes and backend services are NOT implemented in Phase 3. The following Flux query templates define the exact queries that Phase 4 will consume:

### 7.1 Latest Telemetry for a Specific Motor
```flux
from(bucket: "motor_telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01")
  |> last()
```

### 7.2 Motor Health Index Trend (Historical)
```flux
from(bucket: "motor_telemetry")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01" and r._field == "health_index")
```

### 7.3 Motor RUL Trend (Historical)
```flux
from(bucket: "motor_telemetry")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01" and r._field == "rul_hours")
```

### 7.4 Motor Fault History
```flux
from(bucket: "motor_telemetry")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01" and r._field == "fault_type")
```

### 7.5 Fleet Overview (Latest Telemetry for All Motors)
```flux
from(bucket: "motor_telemetry")
  |> range(start: -1h)
  |> filter(fn: (r) => r._measurement == "predictions")
  |> group(columns: ["device_id", "_field"])
  |> last()
```

### 7.6 Telemetry over a Custom Time Range
```flux
from(bucket: "motor_telemetry")
  |> range(start: 2026-09-13T00:00:00Z, stop: 2026-09-13T23:59:59Z)
  |> filter(fn: (r) => r._measurement == "predictions" and r.device_id == "motor_01")
```

---

## 8. Deployment & Operation Instructions

### 8.1 Windows Local Setup
1. Download and start InfluxDB v2.7.12:
   ```powershell
   .\scripts\setup_influxdb_windows.ps1 -Start -Init
   ```
2. InfluxDB will listen at `http://localhost:8086`.

### 8.2 Raspberry Pi 4 (Debian Bookworm) Setup `[Intended Deployment Target]`
1. Install InfluxDB v2 from official repository:
   ```bash
   sudo apt-get update && sudo apt-get install -y influxdb2
   sudo systemctl enable influxdb
   sudo systemctl start influxdb
   ```
2. Initialize database:
   ```bash
   python scripts/init_influxdb.py
   ```

### 8.3 Querying Stored Telemetry
Run the verification query utility:
```powershell
python scripts/query_influxdb.py
```
