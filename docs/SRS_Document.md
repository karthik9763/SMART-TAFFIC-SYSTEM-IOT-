# Software Requirements Specification (SRS)
## Smart Traffic Density Prediction using IoT and Deep Neural Networks (DNN)

### 1. Introduction
#### 1.1 Purpose
This document defines the functional and non-functional requirements for the Smart Traffic Density Prediction System.

#### 1.2 Scope
The system processes live camera feeds (ESP32-CAM, webcam, RTSP, or sample traffic video), counts vehicles, classifies density into Low, Medium, and High using a Deep Neural Network (DNN), and renders live telemetry, charts, PDF reports, and congestion alerts on a web interface.

---

### 2. Functional Requirements
- **FR-01 User Authentication:** Secure login & registration with hashed passwords (`werkzeug.security`) and role-based access (Admin / User).
- **FR-02 Live Stream Ingestion:** Ingest MJPEG video streams from ESP32-CAM or RTSP cameras.
- **FR-03 Real-Time Vehicle Detection:** Detect moving vehicles and annotate bounding boxes with category labels (Cars, Buses, Trucks, Motorbikes).
- **FR-04 Traffic Density Prediction:** DNN inference engine classifies traffic into Low (<=5), Medium (6-12), and High (>12).
- **FR-05 Alert Notification System:** Automatically trigger alert records when traffic density transitions to High.
- **FR-06 Analytics & PDF Export:** Render Chart.js trend graphs and download formatted PDF reports.
- **FR-07 User & Camera Management:** Admin CRUD interface for users and camera endpoints.

---

### 3. Non-Functional Requirements
- **NFR-01 Performance:** Real-time video processing latency < 40 ms per frame.
- **NFR-02 Reliability:** System operates continuously without memory leaks.
- **NFR-03 Security:** Protection against unauthorized route access using `@login_required` decorators.
- **NFR-04 Usability:** Glassmorphic dark theme responsive UI suitable for control rooms.
- **NFR-05 Cost & Open Source:** 100% free and open-source tech stack (Python, OpenCV, Flask, SQLite, Bootstrap 5).

---

### 4. System Interface Requirements
- **Hardware Interface:** ESP32-CAM Wi-Fi Module (HTTP MJPEG Stream over port 81).
- **Software Interface:** Python 3.10+, OpenCV 4.8+, SQLite 3, Bootstrap 5.
