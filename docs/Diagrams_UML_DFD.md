# UML Diagrams & Data Flow Diagrams (DFD)

## 1. System Architecture Diagram

```mermaid
graph TD
    A["ESP32-CAM / CCTV Feed"] -->|MJPEG Video Stream| B["OpenCV + YOLO Detector"]
    B -->|Vehicle detections| C["Density Classifier"]
    C -->|Predicted traffic level| E["Flask REST API"]
    I["ESP32 IR Counter / Wokwi"] -->|MQTT traffic topics| J["Mosquitto Broker"]
    J --> K["Authenticated MQTT Bridge"]
    K -->|Validated device telemetry| E
    E -->|Read / Write| F[("SQLAlchemy Database")]
    E -->|REST + session auth| G["Flask UI / React Operations"]
    G --> H["Traffic Operator / Admin"]
```

---

## 2. Data Flow Diagram (DFD)

### DFD Level 0 (Context Diagram)

```mermaid
graph TD
    Operator["Traffic Operator / Admin"] <-->|Credentials & Dashboard View| System["Smart Traffic System"]
    ESP32["ESP32-CAM / Camera"] -->|Video Feed| System
    System -->|Alerts & Reports| Operator
```

### DFD Level 1

```mermaid
graph TD
    P1["1. User Authentication"]
    P2["2. Camera Image Processing"]
    P3["3. Density Estimation"]
    P4["4. MQTT Device Ingestion"]
    P5["5. Alert & Report Generator"]

    User["Operator / Admin"] -->|Login Info| P1
    P1 -->|User Session| DB[("Database")]
    Cam["Camera Source"] -->|Frames| P2
    P2 -->|Vehicle detections| P3
    P3 -->|Density estimate| DB
    Device["ESP32 / Wokwi"] -->|MQTT| Broker["Mosquitto"]
    Broker -->|Device topics| P4
    P4 -->|Authenticated telemetry/events| DB
    P3 -->|High density signal| P5
    P4 -->|Device alert| P5
    P5 -->|Alert record| DB
    DB -->|Analytics & Reports| User
```

---

## 3. Entity-Relationship (ER) Diagram

```mermaid
erDiagram
    USERS ||--o{ LOGIN_HISTORY : logs
    CAMERA_DETAILS ||--o{ TRAFFIC_RECORDS : captures
    CAMERA_DETAILS ||--o{ ALERTS : triggers
    TRAFFIC_RECORDS ||--o{ PREDICTIONS : evaluates
    IOT_DEVICES ||--o{ IOT_TELEMETRY : reports
    IOT_DEVICES ||--o{ IOT_ALERTS : triggers
    IOT_DEVICES ||--o{ IOT_MQTT_EVENTS : publishes

    USERS {
        int id PK
        string username
        string email
        string password_hash
        string role
    }

    CAMERA_DETAILS {
        int id PK
        string name
        string location
        string stream_url
        string status
    }

    TRAFFIC_RECORDS {
        int id PK
        int camera_id FK
        int vehicle_count
        string density_status
        float average_speed_kmh
        datetime timestamp
    }

    ALERTS {
        int id PK
        int camera_id FK
        string alert_type
        string message
        boolean acknowledged
    }

    IOT_DEVICES {
        string device_id PK
        string intersection_id
        string lane_id
        string mode
        int total_vehicle_count
        datetime last_seen
    }

    IOT_TELEMETRY {
        int id PK
        string device_id FK
        int sequence
        int total_vehicle_count
        string density
        datetime timestamp
    }

    IOT_MQTT_EVENTS {
        int id PK
        string device_id FK
        string topic
        string payload_json
        datetime timestamp
    }
```

---

## 4. Use Case Diagram

```mermaid
graph LR
    Operator((Traffic Operator))
    Admin((Administrator))

    Operator --> UC1["View Dashboard & Telemetry"]
    Operator --> UC2["Monitor Live Video Feed"]
    Operator --> UC3["Export PDF Reports"]
    Operator --> UC4["Acknowledge Alerts"]

    Admin --> UC1
    Admin --> UC2
    Admin --> UC3
    Admin --> UC4
    Admin --> UC5["Manage System Users"]
    Admin --> UC6["Configure Density Thresholds"]
```

---

## 5. Sequence Diagram (Live Monitor & DNN Inference)

```mermaid
sequenceDiagram
    autonumber
    actor Operator
    participant UI as Web Dashboard
    participant Backend as Flask App
    participant CV as OpenCV Engine
    participant DNN as DNN Classifier
    participant DB as SQLite DB

    Operator->>UI: Select Live Camera Endpoint
    UI->>Backend: Request Stream (/video_feed/1)
    loop Every Frame
        Backend->>CV: Read Video Frame
        CV->>CV: Run Motion Detection & Vehicle Count
        CV->>DNN: Send Features (Count, Occupancy, Speed)
        DNN-->>Backend: Return Class ('High', Conf: 96%)
        Backend->>DB: Log Traffic Record & Trigger Alert (if High)
        Backend-->>UI: Stream MJPEG Frame & Live Telemetry JSON
    end
    UI-->>Operator: Display Annotated Video & Alert Badge
```

---

## 6. Activity Diagram (Traffic Density Classification Flow)

```mermaid
stateDiagram-v2
    [*] --> CaptureFrame
    CaptureFrame --> PreprocessFrame: Grayscale & Gaussian Blur
    PreprocessFrame --> BackgroundSubtraction: Motion Thresholding
    BackgroundSubtraction --> ContourDetection: Extract Bounding Boxes
    ContourDetection --> CountVehicles: Categorize Cars/Buses/Trucks
    CountVehicles --> ExtractFeatures: Calculate Occupancy & Speed
    ExtractFeatures --> DNNInference: Pass Features to DNN Model
    DNNInference --> CheckDensity: Evaluate Prediction Class
    
    state CheckDensity {
        [*] --> LowDensity
        [*] --> MediumDensity
        [*] --> HighDensity
    }
    
    HighDensity --> TriggerAlert: Vehicle Count > Threshold
    TriggerAlert --> SaveToDatabase
    LowDensity --> SaveToDatabase
    MediumDensity --> SaveToDatabase
    SaveToDatabase --> [*]
```
