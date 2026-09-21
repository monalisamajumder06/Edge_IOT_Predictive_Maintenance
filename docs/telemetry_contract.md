# Edge-to-Backend Telemetry Contract
## Version: v0.1-draft (Phase 1 Baseline)

---

## 1. Specification Overview

This document defines the formal software contract for telemetry transmitted from the edge inference subsystem (or dummy test publisher) to the Member 3 ingestion pipeline.

The contract defines the structure, data types, semantics, and boundary rules for motor health predictions.

---

## 2. Project-Specified Core Contract

The baseline project specification provides the following canonical telemetry JSON payload:

```json
{
    "device_id": "motor_01",
    "fault_type": "Inner_Race",
    "health_index": 0.88,
    "rul_hours": 420
}
```

### 2.1 Core Field Specifications

| Field Name | Type | Presence | Semantic Meaning | Valid Range / Constraints | Example | Upstream Producer | Downstream Consumer | Category |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `device_id` | `string` | **Required** | Unique identifier of the monitored motor | Non-empty alphanumeric/underscore string | `"motor_01"` | Edge MCU / Gateway | InfluxDB (Tag), FastAPI, Dashboard | `[PROJECT REQUIREMENT]` |
| `fault_type` | `string` | **Required** | Primary diagnostic fault classification | Non-empty classification label | `"Inner_Race"` | Edge TinyML model (M2) | InfluxDB (Field), FastAPI, Dashboard | `[PROJECT REQUIREMENT]` |
| `health_index` | `number` (float) | **Required** | Composite indicator of motor health | Numerical float (e.g. 0.88). *Range [0.0, 1.0] is a recommended assumption* | `0.88` | Edge TinyML model (M2) | InfluxDB (Field), FastAPI, Dashboard | `[PROJECT REQUIREMENT]` |
| `rul_hours` | `number` (int/float) | **Required** | Remaining Useful Life in operating hours | Numerical value. *Non-negative is a recommended assumption* | `420` | Edge RUL model (M2) | InfluxDB (Field), FastAPI, Dashboard | `[PROJECT REQUIREMENT]` |

---

## 3. Ambiguities & Open Decisions

### 3.1 Multi-Label Fault Representation `[OPEN DECISION]`
* **Project Context**: The overall project architecture states that fault classification is conceptually **multi-label** (i.e., a motor may exhibit both bearing defect and stator overheating simultaneously). However, the example payload provides a single string field: `"fault_type": "Inner_Race"`.
* **Status**: Unfinalized. Requires formal coordination with Member 2.
* **Phase 1 Decision**: 
  - The core telemetry schema validates `fault_type` as a string, matching the project specification.
  - Speculative fields such as `fault_labels` (list of strings) or `fault_probabilities` (dictionary) are **not** frozen or required in the core schema.
* **Evaluated Future Alternatives (For Team Discussion Only)**:
  - *Alternative A (Current)*: Single string representing the dominant/highest-confidence fault class.
  - *Alternative B (List)*: An array of active fault labels, e.g. `"fault_types": ["Inner_Race", "Overheating"]`.
  - *Alternative C (Probability Map)*: A dictionary mapping all classes to probabilities, e.g. `"fault_scores": {"Inner_Race": 0.88, "Normal": 0.05}`.

### 3.2 Health Index Range & Semantics `[RECOMMENDATION]`
* **Project Context**: The project specifies an example value of `0.88`. It does not explicitly define minimum, maximum, or directionality.
* **Status**: Range `[0.0, 1.0]` (where 1.0 = pristine health, 0.0 = total failure) is a **recommended implementation assumption**.
* **Phase 1 Decision**: Documented as an engineering recommendation requiring Member 2 confirmation. The validation schema isolates range enforcement into a recommended validation layer to prevent blocking integration if Member 2 adopts an alternative scale (e.g., 0 to 100).

### 3.3 RUL Validation Constraints `[RECOMMENDATION]`
* **Project Context**: The project gives `420` (hours) without stating whether negative values are permitted during over-run states or if fractional hours are emitted.
* **Status**: Restricting `rul_hours >= 0` is a **validation recommendation**, not an explicit project specification.
* **Phase 1 Decision**: Permissive float/int validation in base contract; non-negative check handled as a recommended validation rule.

### 3.4 Timestamp Ingestion Ownership `[OPEN DECISION]`
* **Project Context**: InfluxDB requires a timestamp for all time-series points. The edge example payload does not include a timestamp field.
* **Status**: Open decision regarding whether the edge MCU has access to synchronized time (NTP/RTC) or if the Raspberry Pi Gateway / FastAPI assigns the timestamp upon arrival.
* **Recommended Implementation Choice (Requires Team Agreement)**:
  - If the edge device emits an ISO-8601 UTC `timestamp`, downstream preserves it.
  - If omitted (as in the project example), the gateway/backend ingestion layer injects the current UTC timestamp (`datetime.now(timezone.utc)`).

---

## 4. Optional / Recommended Future Metadata `[RECOMMENDATION / FUTURE WORK]`

The following fields are **strictly excluded from the core contract** for Phase 1. They are documented here solely as potential additions for future phases should Member 2 or Member 1 request them:

* `timestamp` (`string ISO-8601`, e.g., `"2026-09-13T07:45:00Z"`): Edge-synchronized capture timestamp.
* `inference_time_ms` (`float`): Edge execution duration for benchmarking.
* `confidence` (`float`): Model classification confidence score.
* `model_version` (`string`): Quantized model version identifier.

---

## 5. Contract Evolution & Versioning Strategy `[IMPLEMENTATION DECISION]`

To ensure stability across the distributed team, this contract evolves under the following rules:

1. **Current Version**: `v0.1-draft`.
2. **Backwards Compatibility**:
   - The four core fields (`device_id`, `fault_type`, `health_index`, `rul_hours`) must remain supported.
   - Any downstream consumer must tolerate additional optional fields without crashing.
3. **Breaking Changes**:
   - Renaming or removing any core field is a breaking change requiring mutual agreement across Members 1, 2, and 3.
   - Changing data types (e.g. converting `health_index` to a string) is a breaking change.
4. **Coordination Triggers with Member 2**:
   - When Member 2 finalizes the multi-label TinyML output structure, the team will review whether to adopt an updated contract version (`v0.2`).
   - Downstream interfaces (FastAPI and InfluxDB schema) will be designed with flexible field mapping to minimize refactoring upon version updates.
