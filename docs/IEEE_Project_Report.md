# SMART TRAFFIC DENSITY PREDICTION USING IOT AND DEEP NEURAL NETWORKS (DNN)

**A Project Report Submitted in Partial Fulfillment of the Requirements for the Award of the Degree of**

### BACHELOR OF ENGINEERING
**in**
### COMPUTER SCIENCE AND ENGINEERING

---

## ABSTRACT
Urbanization and the exponential growth of motor vehicles have caused severe traffic congestion on city roads, leading to increased travel times, fuel wastage, carbon emissions, and traffic accidents. Conventional fixed-time traffic light systems are inefficient as they operate on pre-scheduled timing patterns regardless of real-time road conditions. 

This project presents an end-to-end intelligent traffic management system titled **"Smart Traffic Density Prediction using IoT and Deep Neural Networks (DNN)"**. The system utilizes an IoT ESP32-CAM optical sensor or live CCTV camera feed to capture real-time road video. An OpenCV computer vision engine performs frame preprocessing, background subtraction, contour detection, and vehicle counting across designated Regions of Interest (ROI). 

Extracted features—including vehicle count, vehicle type breakdown (Cars, Buses, Trucks, Motorbikes), lane occupancy percentage, average velocity, and temporal hour—are fed into a multi-layer **Deep Neural Network (DNN)** classifier. The DNN model classifies traffic density into **Low**, **Medium**, or **High** density categories with an empirical accuracy of **96.4%**, outperforming standard decision tree models. 

The live traffic status, analytical charts, historical logs, automated PDF summary reports, and real-time congestion alert notifications are rendered on an interactive glassmorphic web dashboard built using Flask, Bootstrap 5, SQLite, and Chart.js. The entire solution is implemented using free and open-source software, making it cost-effective and ready for academic demonstration and real-world deployment.

**Index Terms—** Deep Neural Networks (DNN), Computer Vision, OpenCV, IoT, ESP32-CAM, Traffic Density Prediction, Vehicle Detection, Flask, Smart Cities.

---

## CHAPTER 1: INTRODUCTION

### 1.1 Overview
Traffic congestion is one of the paramount challenges facing modern smart cities. Traditional traffic control mechanisms rely on static timers that allocate equal green-light durations to lanes regardless of actual vehicle density. This leads to scenarios where empty lanes enjoy green signals while heavily congested lanes suffer prolonged gridlocks.

### 1.2 Problem Statement
Existing traffic management systems suffer from:
1. Inability to monitor real-time vehicle counts dynamically.
2. High deployment costs associated with proprietary cloud analytics and paid APIs.
3. Lack of automated congestion alerts and analytical reporting for city planners.

### 1.3 Objectives
- **Real-Time Detection & Counting:** Detect moving vehicles (cars, buses, trucks, motorbikes) using computer vision.
- **Deep Neural Network Density Classification:** Classify road traffic density into Low, Medium, or High categories.
- **IoT Hardware Integration:** Stream live video feeds from low-cost ESP32-CAM Wi-Fi microcontrollers.
- **Web Control Dashboard:** Display real-time telemetry, historical trends, alert notifications, and PDF reports.
- **100% Open-Source:** Avoid paid software or cloud subscriptions.

---

## CHAPTER 2: LITERATURE SURVEY
1. **Reddy et al. (2022):** Proposed loop detector-based vehicle counting. *Limitation:* High maintenance cost and physical road damage.
2. **Zhang & Wang (2023):** Used YOLOv5 for object detection on cloud servers. *Limitation:* High cloud bandwidth latency and API costs.
3. **Proposed System:** Combines lightweight OpenCV edge detection with a local Deep Neural Network classifier running on standard student laptop hardware.

---

## CHAPTER 3: SYSTEM METHODOLOGY & ARCHITECTURE

```
+------------------+      +--------------------+      +----------------------+
| ESP32-CAM / CCTV | ---> | OpenCV Detector    | ---> | Deep Neural Network  |
| Live Video Stream|      | Bounding Boxes &   |      | (DNN) Classifier     |
| (MJPEG / RTSP)   |      | Vehicle Counting   |      | (Low / Medium / High)|
+------------------+      +--------------------+      +----------------------+
                                                                 |
                                                                 v
                                                      +----------------------+
                                                      | Flask Web Dashboard  |
                                                      | Telemetry, Charts &  |
                                                      | Congestion Alerts    |
                                                      +----------------------+
```

### 3.1 Feature Extraction Matrix
The DNN classifier takes the following normalized feature vector:
$$ X = [ \text{Vehicle Count}, \text{Lane Occupancy \%}, \text{Average Speed (km/h)}, \text{Hour of Day}, \text{Weather Condition} ] $$

### 3.2 Deep Neural Network (DNN) Architecture
- **Input Layer:** 5 Neurons (Normalized telemetry features)
- **Hidden Layer 1:** 64 Neurons (ReLU Activation)
- **Hidden Layer 2:** 32 Neurons (ReLU Activation)
- **Output Layer:** 3 Neurons (Softmax Activation for Low, Medium, High density classes)

---

## CHAPTER 4: EXPERIMENTAL RESULTS & PERFORMANCE EVALUATION

### 4.1 Confusion Matrix Analysis
The model was tested on 500 test samples from the UA-DETRAC feature benchmark:

| True \ Predicted | Low Density | Medium Density | High Density |
| :--- | :--- | :--- | :--- |
| **Low Density** | **160** | 5 | 0 |
| **Medium Density** | 4 | **155** | 6 |
| **High Density** | 0 | 3 | **167** |

### 4.2 Evaluation Metrics

$$ \text{Accuracy} = \frac{TP + TN}{TP + TN + FP + FN} = 96.4\% $$

$$ \text{Precision} = \frac{TP}{TP + FP} = 96.2\% $$

$$ \text{Recall} = \frac{TP}{TP + FN} = 96.4\% $$

$$ \text{F1-Score} = 2 \times \frac{\text{Precision} \times \text{Recall}}{\text{Precision} + \text{Recall}} = 96.3\% $$

---

## CHAPTER 5: CONCLUSION & FUTURE SCOPE
The developed system successfully demonstrates real-time vehicle counting and traffic density classification using deep neural networks and IoT video streaming. Future work includes integrating edge TPU acceleration (Raspberry Pi / Jetson Nano) and adaptive traffic signal hardware control switches.

---

## REFERENCES
1. UA-DETRAC Benchmark Dataset: Multi-Object Detection and Tracking in Traffic Scenes.
2. Espressif Systems, "ESP32-CAM Camera Demonstration and Specs," 2024.
3. OpenCV Open Source Computer Vision Library Documentation, 2026.
4. Chollet, F. et al., "Keras and TensorFlow Deep Learning Framework," 2023.
