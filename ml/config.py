import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
ML_DIR = BASE_DIR / "ml"
MODELS_DIR = ML_DIR / "models"
DATASET_DIR = BASE_DIR / "data" / "ua_detrac"

# Target 7 Vehicle Classes (Dashboard Schema)
TARGET_CLASSES = [
    'Car',           # Class 0
    'Bus',           # Class 1
    'Truck',         # Class 2
    'Motorcycle',    # Class 3
    'Bicycle',       # Class 4
    'Van',           # Class 5
    'Auto-rickshaw'   # Class 6
]

CLASS_NAME_TO_ID = {cls: idx for idx, cls in enumerate(TARGET_CLASSES)}
CLASS_ID_TO_NAME = {idx: cls for idx, cls in enumerate(TARGET_CLASSES)}

# UA-DETRAC Class Mapping to Target Dashboard Schema
UADETRAC_CLASS_MAP = {
    'car': 0,        # Car -> Car (0)
    'bus': 1,        # Bus -> Bus (1)
    'van': 5,        # Van -> Van (5)
    'others': 2,     # Others (Trucks / Heavy Vehicles) -> Truck (2)
    'truck': 2,      # Truck -> Truck (2)
    'motorcycle': 3, # Motorcycle -> Motorcycle (3)
    'bicycle': 4,    # Bicycle -> Bicycle (4)
}

# Training Settings
TRAIN_CONFIG = {
    'epochs': 200,
    'imgsz': 640,
    'batch': -1,            # Automatic Batch Size
    'patience': 30,          # Early Stopping Patience
    'optimizer': 'AdamW',
    'lr0': 0.001,
    'weight_decay': 0.0005,
    'workers': max(1, os.cpu_count() or 4),
    'cache': True,
    'save_best': True,
    'amp': True,            # Mixed Precision
    'cos_lr': True,         # Cosine Learning Rate Scheduler
    'pretrained': True      # Transfer Learning Backbone
}

# Detection & Post-Processing Parameters
DETECTION_CONFIG = {
    'conf_threshold': 0.25,  # Balanced threshold default
    'iou_threshold': 0.45,   # IoU threshold = 0.45 for NMS deduplication
    'imgsz': 1280,           # High-resolution inference
    'min_box_area': 35,      # Capture small distant vehicles (no aggressive dropping)
    'min_box_dim': 5,        # Minimum dimension for distant vehicles
    'display_conf_min': 50.0 # Display confidence % on box only if > 50%
}

# Detection Modes (Fast, Balanced, High Accuracy)
DETECTION_MODES = {
    'fast': {
        'name': 'Fast Mode',
        'imgsz': 640,
        'conf': 0.35,
        'iou': 0.45,
        'clahe': False,
        'sharpen': False,
        'sahi': False,
        'augment': False
    },
    'balanced': {
        'name': 'Balanced Mode',
        'imgsz': 1280,
        'conf': 0.25,
        'iou': 0.45,
        'clahe': True,
        'sharpen': True,
        'sahi': False,
        'augment': False
    },
    'high_accuracy': {
        'name': 'High Accuracy Mode',
        'imgsz': 1280,
        'conf': 0.15,
        'iou': 0.45,
        'clahe': True,
        'sharpen': True,
        'sahi': True,
        'augment': True
    }
}

# COCO Class IDs for vehicles: 1=bicycle, 2=car, 3=motorcycle, 5=bus, 7=truck
COCO_VEHICLE_CLASS_IDS = [1, 2, 3, 5, 7]

# Traffic Density Categorization Rules (Per-Frame Count & Occupancy)
# Levels: Low, Medium, High, Very High
DENSITY_THRESHOLDS = {
    'LOW_MAX': 5,        # 0 – 5 vehicles -> Low
    'MEDIUM_MAX': 14,    # 6 – 14 vehicles -> Medium
    'HIGH_MAX': 25,      # 15 – 25 vehicles -> High
    'VERY_HIGH_MIN': 26  # > 25 vehicles -> Very High
}
DENSITY_LEVELS = ['Low', 'Medium', 'High', 'Very High']


# Ensure directories exist
MODELS_DIR.mkdir(parents=True, exist_ok=True)
DATASET_DIR.mkdir(parents=True, exist_ok=True)
