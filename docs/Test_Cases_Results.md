# Software Test Cases & Empirical Performance Analysis

## 1. Unit & Functional Test Suite

| Test ID | Test Scenario | Input Data | Expected Result | Actual Result | Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **TC-01** | User Authentication Login | `admin / admin123` | Redirects to Dashboard with Admin session | Successfully logged in as Admin | **PASS** |
| **TC-02** | Invalid Login Attempt | `admin / wrongpass` | Display warning flash message | Flash message rendered: Invalid credentials | **PASS** |
| **TC-03** | Live Video Ingestion | Demo MP4 / USB Webcam | Video stream renders with green/yellow bounding boxes | Stream renders @ 25+ FPS with detection overlay | **PASS** |
| **TC-04** | Vehicle Counting Accuracy | Frame with 10 vehicles | Detector identifies 9-10 vehicles | Count: 10 vehicles detected | **PASS** |
| **TC-05** | DNN Model Inference | Count: 18, Occupancy: 65% | Classified as **HIGH TRAFFIC** | Output: **HIGH** (96.8% confidence) | **PASS** |
| **TC-06** | Congestion Alert Generation | High density trigger | Alert record inserted into DB & Alert Badge pulses red | Alert logged in database & rendered on UI | **PASS** |
| **TC-07** | PDF Report Generation | Click "Export PDF" | PDF window opens with formatted executive summary | PDF preview generated successfully | **PASS** |
| **TC-08** | Unauthorized Route Guard | Unauthenticated access to `/dashboard` | Redirects to `/login` with warning | Redirected to `/login` | **PASS** |

---

## 2. Model Performance Evaluation Matrix

> The historical performance figures below are retained from prior project
> documentation. They were not regenerated as part of the MQTT/Wokwi/React
> integration; the current integration verification is listed in section 3.

### Tested Dataset
- **Dataset Source:** UA-DETRAC Benchmark & Synthesized Traffic Feature Distribution
- **Total Samples:** 2,500 samples (80% Train: 2,000 / 20% Test: 500)
- **Classifier Model:** Deep Neural Network (MLP: 5 -> 64 -> 32 -> 3)

### Confusion Matrix Breakdown (500 Test Samples)

| Actual \ Predicted | Low Density | Medium Density | High Density | Total |
| :--- | :--- | :--- | :--- | :--- |
| **Low Density** | **160** | 5 | 0 | 165 |
| **Medium Density** | 4 | **155** | 6 | 165 |
| **High Density** | 0 | 3 | **167** | 170 |
| **Total** | 164 | 163 | 173 | **500** |

### Mathematical Metrics Summary

- **Overall Accuracy:** **96.4%**
- **Weighted Precision:** **96.2%**
- **Weighted Recall:** **96.4%**
- **Weighted F1-Score:** **96.3%**
- **Average Inference Latency:** **1.8 ms / sample**

### Metric Formulas Applied
$$ \text{Accuracy} = \frac{160 + 155 + 167}{500} = \frac{482}{500} = 0.964 \ (96.4\%) $$

## 3. MQTT, Wokwi, and React Integration Validation

Validation performed on 2026-10-23:

| Check | Result | Evidence |
| --- | --- | --- |
| Flask MQTT-event token validation and event persistence | PASS | `python -m unittest discover -s tests -v` |
| Telemetry validation/persistence and secret redaction | PASS | In-memory SQLite API tests |
| MQTT bridge forwarding, 4xx handling, and transient retry behavior | PASS | Mocked HTTP bridge tests |
| React session/CSRF API and operations route | PASS | Flask test client |
| React sign-in, operations dashboard, and density form | PASS | Browser smoke test against temporary Flask/SQLite; prediction returned HTTP 200 |
| Wokwi JSON/configuration structure | PASS | Both diagrams parse; expected board/pin assertions pass |
| React production bundle | PASS | `npm --prefix client run build` |
| Frontend dependency audit | PASS | `npm audit` reported 0 vulnerabilities |
| Python syntax compilation | PASS | `python -m compileall -q app.py database.py server tests` |
| Arduino firmware compilation / Wokwi simulator | NOT RUN | Arduino CLI and Wokwi CLI/token are not available in this environment |
| Physical sensors, MQTT broker, and ESP32-CAM imaging | NOT RUN | Requires hardware and a configured reachable broker |
