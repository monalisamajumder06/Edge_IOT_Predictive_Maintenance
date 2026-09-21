# Integration Contracts & Open Decisions Matrix
## Subsystem: IoT + Backend + Dashboard (Member 3)

This document establishes the formal register of integration agreements, implementation choices, and open coordination points between Member 3, Member 1 (Sensors + DSP), and Member 2 (Machine Learning + TinyML).

---

## Category A: Fixed by Project Specification `[PROJECT REQUIREMENT]`

These items are explicitly defined in project documentation and represent immutable architectural constraints:

1. **Assigned Member 3 Stack**:
   - Raspberry Pi Gateway
   - Mosquitto MQTT Broker
   - Node-RED routing & buffering
   - InfluxDB time-series storage
   - FastAPI application backend
   - Grafana or Streamlit dashboard
2. **Canonical Telemetry Fields**:
   - The edge-to-IoT interface must deliver at minimum:
     - `device_id`: string (e.g. `"motor_01"`)
     - `fault_type`: string (e.g. `"Inner_Race"`)
     - `health_index`: numerical value (e.g. `0.88`)
     - `rul_hours`: numerical value (e.g. `420`)
3. **Decoupled Development Workflow**:
   - The platform must be constructed with mock/dummy predictions first, verifying the software pipeline independently before connecting physical edge MCU hardware.
4. **Multi-Label Concept**:
   - Motor fault classification is conceptually multi-label (multiple degradation modes can co-exist).

---

## Category B: Recommended Implementation Choices `[RECOMMENDATION]`

These are engineering decisions proposed by Member 3 to build a robust, scalable system. They are sensible defaults but subject to team agreement:

1. **MQTT Topic Hierarchy**:
   - Topic convention: `motors/{device_id}/prediction` for inferences and `motors/{device_id}/status` for connection state.
2. **MQTT Quality of Service**:
   - QoS 1 (At least once delivery) selected for prediction telemetry to prevent loss of critical failure alerts over wireless networks.
3. **Health Index Range**:
   - Normalized continuous range `[0.0, 1.0]` (where 1.0 = pristine health, 0.0 = failure) is adopted as a recommended validation rule.
4. **Non-Negative RUL Constraint**:
   - Enforcing `rul_hours >= 0` is adopted as a recommended validation rule.
5. **Timestamp Fallback Mechanism**:
   - If the edge device does not transmit an ISO-8601 `timestamp` field, the Raspberry Pi Gateway or FastAPI ingestion layer attaches the arrival UTC timestamp before writing to InfluxDB.
6. **Data Storage Granularity**:
   - InfluxDB bucket `motor_telemetry` retaining raw predictions for 30 days, downsampled to hourly aggregates for long-term RUL tracking.

---

## Category C: Decisions Requiring Coordination with Member 1 `[OPEN DECISION]`

1. **Raw Sensor vs. Feature Ingestion**:
   - *Question*: Will Member 3's gateway ever receive raw sensor features (RMS, FFT peak frequencies, Log-Mel spectrograms) for dashboard display, or strictly inference outputs?
   - *Working Assumption*: Only inference outputs are transmitted over MQTT to preserve edge bandwidth; raw features remain on the MCU unless a debug topic is explicitly agreed upon.
2. **Windowing and Publishing Cadence**:
   - *Question*: With 1-second windows and 50% overlap, will inference results be emitted every 0.5 seconds or averaged to a 1.0-second publication rate?
   - *Working Assumption*: Member 3 backend expects approximately 1 message per second per motor.

---

## Category D: Decisions Requiring Coordination with Member 2 `[OPEN DECISION]`

1. **Multi-Label Fault Representation Structure**:
   - *Question*: How will the multi-label output from the 1D Depthwise Separable CNN be serialized into JSON?
     - *Alternative 1 (Current)*: Single string in `fault_type` representing the top predicted class.
     - *Alternative 2*: Array of triggered faults, e.g. `"fault_types": ["Inner_Race", "Eccentricity"]`.
     - *Alternative 3*: Dictionary of probabilities, e.g. `"fault_probabilities": {"Normal": 0.05, "Inner_Race": 0.91, "Eccentricity": 0.42}`.
   - *Working Assumption*: For Phase 1, only `fault_type` (string) is enforced. No speculative multi-label schema is frozen until Member 2 finalizes model output formatting.
2. **RUL Units and Uncertainty Bounds**:
   - *Question*: Does the RUL model output integer operating hours or floating-point hours? Will it provide confidence intervals (e.g. `[rul_min, rul_max]`)?
   - *Working Assumption*: `rul_hours` is accepted as float or integer; confidence bounds are treated as future optional metadata.
3. **Model Warm-Up & Initial Prediction Handling**:
   - *Question*: What does the model emit during the first few seconds of motor spin-up before sufficient sliding windows accumulate?
   - *Working Assumption*: Initial readings emit `fault_type: "Unknown"` or `"Calibrating"` with `health_index: 1.0`.

---

## Category E: Decisions That Can Be Finalized Later `[FUTURE WORK]`

1. **Authentication & TLS on Local Broker**:
   - Adding username/password and TLS certificates on Mosquitto (deferred until physical Wi-Fi deployment on Raspberry Pi in Phase 2).
2. **Dashboard Visual Technology Final Selection**:
   - Choosing between Grafana (turnkey time-series dashboards) vs. Streamlit (custom Python ML visualizations) or running both side-by-side.
3. **Alerting & Notification Integrations**:
   - Email/Telegram/SMS alerts triggered when `health_index < 0.3` or `rul_hours < 24` (Phase 3).
4. **Historical Downsampling Retention Policies**:
   - Long-term continuous aggregation queries in InfluxDB (Phase 3).
