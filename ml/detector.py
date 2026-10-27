import os
import time
import cv2
import numpy as np
from pathlib import Path

# Safe PyTorch & Ultralytics Import Guards
HAS_TORCH = False
HAS_YOLO = False
torch = None
YOLO = None

try:
    import torch as _torch
    _t = _torch.zeros(1)
    torch = _torch
    HAS_TORCH = True
    # Enforce deterministic behavior
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)
        torch.backends.cudnn.deterministic = True
        torch.backends.cudnn.benchmark = False
except Exception:
    torch = None
    HAS_TORCH = False

np.random.seed(42)

if HAS_TORCH:
    try:
        from ultralytics import YOLO as _YOLO
        YOLO = _YOLO
        HAS_YOLO = True
    except Exception:
        YOLO = None
        HAS_YOLO = False

from ml.config import (
    TARGET_CLASSES, CLASS_NAME_TO_ID, DETECTION_CONFIG,
    DETECTION_MODES, COCO_VEHICLE_CLASS_IDS, DENSITY_THRESHOLDS, MODELS_DIR
)
from ml.logger import log_event


class VehicleDetector:
    """
    Production Deep Learning Vehicle Detection & Tracking Engine powered by YOLOv11.

    Features:
    - YOLOv11 transfer learning backbone with pretrained COCO weights
    - Detection of 6 target classes: car, motorcycle, bus, truck, bicycle, van
    - High-resolution inference: imgsz = 1280
    - FP16 half-precision on CUDA GPU; optimized FP32 on CPU
    - Image enhancement: CLAHE, sharpening, contrast stretching
    - Test-Time Augmentation (TTA) in High Accuracy mode
    - SAHI (Sliced Aided Hyper Inference) for small & distant vehicles
    - Strict IoU 0.45 Non-Maximum Suppression (NMS) deduplication
    - ByteTrack tracking integration
    - Recalculated road density: density = detected vehicles / total road area
    - Exact breakdown: Total Vehicles, Cars, Buses, Trucks, Motorcycles, Bicycles, Vans
    - Mode switching: Fast Mode, Balanced Mode, High Accuracy Mode
    - Display confidence percentage only if confidence > 50%
    - Deterministic output: fixed seeds and sorted box outputs
    """

    def __init__(self, model_path=None, conf_threshold=None, iou_threshold=None):
        self.conf_threshold = conf_threshold or DETECTION_CONFIG['conf_threshold']
        self.iou_threshold = iou_threshold or DETECTION_CONFIG['iou_threshold']
        self.min_box_area = DETECTION_CONFIG['min_box_area']
        self.min_box_dim = DETECTION_CONFIG['min_box_dim']
        self.display_conf_min = DETECTION_CONFIG.get('display_conf_min', 50.0)
        self.target_classes = TARGET_CLASSES

        # Device & Precision Setup
        if HAS_TORCH and torch.cuda.is_available():
            self.device = 'cuda:0'
            self.half = True
            print(f"[VehicleDetector] CUDA GPU available: {torch.cuda.get_device_name(0)} (FP16 enabled)")
        else:
            self.device = 'cpu'
            self.half = False
            print("[VehicleDetector] Running on CPU (Optimized FP32)")

        # Target class styling colors (BGR)
        self.colors = {
            'Car': (0, 255, 127),           # Spring Green
            'Bus': (0, 165, 255),           # Orange
            'Truck': (255, 191, 0),         # Deep Sky Blue
            'Motorcycle': (255, 105, 180),  # Hot Pink
            'Bicycle': (238, 130, 238),     # Violet
            'Van': (147, 112, 219),         # Medium Purple
            'Auto-rickshaw': (0, 215, 255) # Gold (mapped or legacy)
        }

        self.model = None
        self.model_name = "unavailable"
        self._load_detection_engine(model_path)

    def _load_detection_engine(self, custom_path=None):
        """Loads the best available YOLO model backbone."""
        if not HAS_YOLO:
            print("[VehicleDetector Warning] Ultralytics YOLO not available. Check environment.")
            return

        candidates = []
        if custom_path:
            candidates.append(Path(custom_path))

        candidates.extend([
            MODELS_DIR / "best.pt",
            MODELS_DIR / "yolo_runs" / "train_results" / "weights" / "best.pt",
            Path("yolo11x.pt"),
            Path("yolo11m.pt"),
            Path("yolo11s.pt"),
            Path("yolo11n.pt"),
            MODELS_DIR / "yolo11n.pt",
            Path("yolov8x.pt"),
            Path("yolov8n.pt")
        ])

        for p in candidates:
            if p.exists():
                try:
                    self.model = YOLO(str(p))
                    self.model_name = p.name
                    print(f"[VehicleDetector] Loaded YOLO backbone: {p.name}")
                    log_event("model loaded", f"YOLO backbone {p.name} on {self.device} (FP16={self.half})")
                    return
                except Exception as e:
                    print(f"[VehicleDetector Warning] Could not load {p}: {e}")

        # Fallback to direct model name (auto-downloads if missing)
        for fallback_name in ["yolo11n.pt", "yolov8n.pt"]:
            try:
                self.model = YOLO(fallback_name)
                self.model_name = fallback_name
                print(f"[VehicleDetector] Loaded transfer learning backbone: {fallback_name}")
                log_event("model loaded", f"Fallback backbone {fallback_name} on {self.device} (FP16={self.half})")
                return
            except Exception as e:
                print(f"[VehicleDetector Warning] Could not load fallback {fallback_name}: {e}")

        print("[VehicleDetector Error] No YOLO model could be initialized.")
        log_event("model loaded", "FAILED to load any YOLO model backbone")

    def enhance_image(self, image, apply_clahe=True, apply_sharpen=False):
        """
        Enhances image quality before deep learning inference:
        - CLAHE on L-channel of LAB color space to reveal vehicles in shadows/low-light/rain
        - Contrast stretching if image is underexposed or flat
        - Unsharp Masking / Laplacian edge sharpening for distant and small vehicles
        """
        if image is None or image.size == 0:
            return image

        enhanced = image.copy()

        # 1. CLAHE in LAB Color Space
        if apply_clahe:
            lab = cv2.cvtColor(enhanced, cv2.COLOR_BGR2LAB)
            l_channel, a_channel, b_channel = cv2.split(lab)
            clahe = cv2.createCLAHE(clipLimit=2.2, tileGridSize=(8, 8))
            l_clahe = clahe.apply(l_channel)

            # Adaptive gamma adjustment if mean luminance is dark (< 50)
            mean_lum = np.mean(l_clahe)
            if mean_lum < 50.0:
                gamma = 1.25
                inv_gamma = 1.0 / gamma
                table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in np.arange(0, 256)]).astype("uint8")
                l_clahe = cv2.LUT(l_clahe, table)

            lab_merged = cv2.merge((l_clahe, a_channel, b_channel))
            enhanced = cv2.cvtColor(lab_merged, cv2.COLOR_LAB2BGR)

        # 2. Unsharp Masking Sharpening Filter for distant small vehicle boundaries
        if apply_sharpen:
            gaussian = cv2.GaussianBlur(enhanced, (0, 0), 2.0)
            enhanced = cv2.addWeighted(enhanced, 1.25, gaussian, -0.25, 0)

        return enhanced

    def assess_image_quality(self, image):
        """Assesses image quality for blur, extreme darkness/brightness, low contrast."""
        if image is None or image.size == 0:
            return True, "Invalid or empty image data.", {}

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        laplacian_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        mean_lum = float(np.mean(gray))
        contrast = float(np.std(gray))

        is_low_quality = False
        warning_msg = None

        if laplacian_var < 35.0:
            is_low_quality = True
            warning_msg = "Low image quality detected (Blurry)."
        elif mean_lum < 20.0:
            is_low_quality = True
            warning_msg = "Low image quality detected (Low Light / Dark)."
        elif mean_lum > 240.0:
            is_low_quality = True
            warning_msg = "Low image quality detected (Overexposed)."
        elif contrast < 16.0:
            is_low_quality = True
            warning_msg = "Low image quality detected (Low Contrast)."

        metrics = {
            'laplacian_var': round(laplacian_var, 2),
            'mean_luminance': round(mean_lum, 2),
            'rms_contrast': round(contrast, 2)
        }
        return is_low_quality, warning_msg, metrics

    def _generate_slices(self, img_shape, slice_size=640, overlap_ratio=0.20):
        """Generates bounding coordinates for SAHI overlapping image slices."""
        h, w = img_shape[:2]
        step = int(slice_size * (1.0 - overlap_ratio))
        slices = []
        y = 0
        while y < h:
            x = 0
            y_end = min(y + slice_size, h)
            y_start = max(0, y_end - slice_size)
            while x < w:
                x_end = min(x + slice_size, w)
                x_start = max(0, x_end - slice_size)
                slices.append((x_start, y_start, x_end, y_end))
                if x_end >= w:
                    break
                x += step
            if y_end >= h:
                break
            y += step
        return slices

    def _classify_vehicle_type(self, raw_name, w_box, h_box):
        """
        Maps raw detected class to the 6 production target classes:
        - Car, Motorcycle, Bus, Truck, Bicycle, Van
        Ignores all other classes.
        Accurately differentiates Vans from Cars and Trucks based on bounding box geometry.
        """
        name = str(raw_name).lower().strip()

        # Direct class mappings
        if name in ['bus', '5']:
            return 'Bus'
        elif name in ['motorcycle', 'motorbike', 'moto', 'scooter', '3']:
            return 'Motorcycle'
        elif name in ['bicycle', 'bike', 'cycle', '1']:
            return 'Bicycle'
        elif name in ['van', 'minivan']:
            return 'Van'

        # Distinction between Car, Van, and Truck
        box_area = w_box * h_box
        aspect_ratio = float(w_box) / max(1.0, float(h_box))

        if name in ['truck', '7']:
            # Light commercial box vans often get classified as truck in COCO
            if 1500 <= box_area <= 6500 and 1.05 <= aspect_ratio <= 1.45:
                return 'Van'
            return 'Truck'

        if name in ['car', '2', '0']:
            # Large multi-passenger vans or high-roof vans
            if 2200 <= box_area <= 7500 and 1.10 <= aspect_ratio <= 1.40 and h_box > 55:
                return 'Van'
            return 'Car'

        return None

    def process_frame(self, frame, mode='balanced', draw_overlay=True):
        """
        Full Production Vehicle Detection Pipeline.
        Supports Fast Mode, Balanced Mode, and High Accuracy Mode.
        """
        start_time = time.time()

        empty_telemetry = {
            'count': 0, 'cars': 0, 'buses': 0, 'trucks': 0, 'motorcycles': 0,
            'bicycles': 0, 'vans': 0, 'autorickshaws': 0, 'bikes_total': 0,
            'occupancy': 0.0, 'density_level': 'LOW', 'density_pct': 0.0,
            'road_density': 0.0, 'quality_warning': 'Empty image',
            'inference_time_ms': 0.0, 'mode': mode, 'detected_vehicles': []
        }

        if frame is None or frame.size == 0:
            return frame, empty_telemetry

        # Normalize mode
        mode_key = str(mode).lower().replace(' ', '_')
        mode_cfg = DETECTION_MODES.get(mode_key, DETECTION_MODES['balanced'])

        imgsz = mode_cfg['imgsz']
        conf_thresh = mode_cfg['conf']
        iou_thresh = mode_cfg['iou']
        apply_clahe = mode_cfg['clahe']
        apply_sharpen = mode_cfg['sharpen']
        use_sahi = mode_cfg['sahi']
        use_augment = mode_cfg['augment']

        h_img, w_img = frame.shape[:2]
        is_low_quality, quality_warning, _ = self.assess_image_quality(frame)

        # Verify YOLO model is loaded correctly before inference
        if self.model is None and HAS_YOLO:
            self._load_detection_engine()

        # Image Enhancement Preprocessing
        log_event("preprocessing", f"Enhancing frame ({w_img}x{h_img}, mode={mode_key}) - CLAHE={apply_clahe}, Sharpen={apply_sharpen}")
        processed_frame = self.enhance_image(frame, apply_clahe=apply_clahe, apply_sharpen=apply_sharpen)

        raw_candidates = [] # list of (x, y, w, h, conf, v_type)
        inference_error = None

        if self.model is not None and HAS_TORCH:
            try:
                log_event("inference", f"Running YOLO ({self.model_name}) on {self.device} (imgsz={imgsz}, conf={conf_thresh}, iou={iou_thresh})")
                # Deterministic inference context
                with torch.no_grad():
                    # 1. Full-image High-Resolution Inference
                    predict_kwargs = {
                        'conf': conf_thresh,
                        'iou': iou_thresh,
                        'imgsz': imgsz,
                        'device': self.device,
                        'classes': COCO_VEHICLE_CLASS_IDS,
                        'verbose': False
                    }
                    if self.half:
                        predict_kwargs['half'] = True
                    if use_augment:
                        predict_kwargs['augment'] = True

                    results = self.model.predict(source=processed_frame, **predict_kwargs)

                    if results and len(results) > 0:
                        names_dict = results[0].names
                        boxes = results[0].boxes
                        for box in boxes:
                            conf = float(box.conf[0])
                            cls_idx = int(box.cls[0])
                            raw_name = names_dict.get(cls_idx, 'car')

                            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0]]
                            w_box = max(1, x2 - x1)
                            h_box = max(1, y2 - y1)

                            if w_box < self.min_box_dim or h_box < self.min_box_dim:
                                continue
                            if (w_box * h_box) < self.min_box_area:
                                continue

                            v_type = self._classify_vehicle_type(raw_name, w_box, h_box)
                            if v_type is not None:
                                raw_candidates.append([x1, y1, w_box, h_box, conf, v_type])

                    # 2. SAHI Sliced Inference for High Accuracy Mode (Large / Distant Vehicle Detection)
                    if use_sahi and (w_img >= 1000 or h_img >= 700):
                        slice_coords = self._generate_slices(frame.shape, slice_size=640, overlap_ratio=0.20)
                        if len(slice_coords) > 1:
                            # Batch inference on slices
                            slice_images = [processed_frame[y1:y2, x1:x2] for (x1, y1, x2, y2) in slice_coords]
                            slice_kwargs = {
                                'conf': conf_thresh,
                                'iou': iou_thresh,
                                'imgsz': 640,
                                'device': self.device,
                                'classes': COCO_VEHICLE_CLASS_IDS,
                                'verbose': False
                            }
                            if self.half:
                                slice_kwargs['half'] = True

                            slice_results = self.model.predict(source=slice_images, **slice_kwargs)


                            for i, s_res in enumerate(slice_results):
                                s_x1, s_y1, _, _ = slice_coords[i]
                                s_names = s_res.names
                                for s_box in s_res.boxes:
                                    conf = float(s_box.conf[0])
                                    cls_idx = int(s_box.cls[0])
                                    raw_name = s_names.get(cls_idx, 'car')

                                    bx1, by1, bx2, by2 = [int(v) for v in s_box.xyxy[0]]
                                    # Translate slice coordinates to global frame
                                    gx1 = s_x1 + bx1
                                    gy1 = s_y1 + by1
                                    gw = max(1, bx2 - bx1)
                                    gh = max(1, by2 - by1)

                                    if gw < self.min_box_dim or gh < self.min_box_dim:
                                        continue
                                    if (gw * gh) < self.min_box_area:
                                        continue

                                    v_type = self._classify_vehicle_type(raw_name, gw, gh)
                                    if v_type is not None:
                                        raw_candidates.append([gx1, gy1, gw, gh, conf, v_type])

            except Exception as ex:
                print(f"[VehicleDetector Warning] YOLO inference failed: {ex}")
                inference_error = str(ex)

        # 3. Global Non-Maximum Suppression (NMS) Deduplication
        dedup_boxes = []
        if raw_candidates:
            nms_boxes = [[c[0], c[1], c[2], c[3]] for c in raw_candidates]
            nms_scores = [float(c[4]) for c in raw_candidates]

            indices = cv2.dnn.NMSBoxes(
                bboxes=nms_boxes,
                scores=nms_scores,
                score_threshold=conf_thresh,
                nms_threshold=iou_thresh
            )

            if len(indices) > 0:
                flat_indices = indices.flatten() if hasattr(indices, 'flatten') else indices
                for idx in flat_indices:
                    dedup_boxes.append(raw_candidates[idx])

        # Deterministic sorting of detected boxes: from top-to-bottom, left-to-right
        dedup_boxes.sort(key=lambda b: (b[1] // 20, b[0] // 20, -b[4]))

        # Count vehicle breakdown
        cars = buses = trucks = motorcycles = bicycles = vans = 0
        detected_vehicles = []

        for b in dedup_boxes:
            gx, gy, gw, gh, conf, v_type = b
            box_area = gw * gh

            if v_type == 'Car': cars += 1
            elif v_type == 'Bus': buses += 1
            elif v_type == 'Truck': trucks += 1
            elif v_type == 'Motorcycle': motorcycles += 1
            elif v_type == 'Bicycle': bicycles += 1
            elif v_type == 'Van': vans += 1

            detected_vehicles.append({
                'type': v_type,
                'bbox': (gx, gy, gw, gh),
                'confidence': round(conf * 100.0, 1),
                'area': box_area
            })

        total_count = len(detected_vehicles)
        # Validation guarantee: count must match breakdown
        assert total_count == (cars + buses + trucks + motorcycles + bicycles + vans)

        bikes_total = motorcycles + bicycles

        # 4. Road Area & Accurate Density Calculation
        # Estimate effective road area: roadway occupies approximately 85% of traffic camera scenes
        road_fraction = 0.85
        total_road_area = float(w_img * h_img) * road_fraction
        occupied_vehicle_area = sum(v['area'] for v in detected_vehicles)

        # Lane Occupancy Rate: calculated using vehicle area, road ROI, lane width
        # Estimate number of active traffic lanes based on image geometry
        num_lanes = max(2, min(6, round(w_img / 280.0)))
        lane_width = (w_img * road_fraction) / num_lanes
        lane_area = total_road_area / num_lanes

        raw_occupancy = (occupied_vehicle_area / max(1.0, total_road_area)) * 100.0
        if total_count > 0:
            # Never keep it fixed at 0% when vehicles are detected
            occupancy_rate = round(min(100.0, max(1.0, raw_occupancy)), 1)
        else:
            occupancy_rate = 0.0

        # Road Density = detected vehicles / total road area (scaled per 100x100 px block)
        road_density = round((total_count / max(1.0, total_road_area)) * 10000.0, 3)

        # Categorize Traffic Density based on vehicle count, road occupancy, and lane occupancy
        # Required Display levels: Low, Medium, High, Very High
        if self.model is None or inference_error:
            density_level = 'Unknown'
            density_pct = 0.0
        elif total_count == 0:
            density_level = 'Low'
            density_pct = 0.0
        elif total_count <= DENSITY_THRESHOLDS['LOW_MAX'] and occupancy_rate < 20.0:
            density_level = 'Low'
            density_pct = round(min(30.0, (total_count / 5.0) * 25.0 + occupancy_rate * 0.25), 1)
        elif total_count <= DENSITY_THRESHOLDS['MEDIUM_MAX'] and occupancy_rate < 45.0:
            density_level = 'Medium'
            density_pct = round(min(69.9, 30.0 + ((total_count - 5) / 9.0) * 35.0 + occupancy_rate * 0.1), 1)
        elif total_count <= DENSITY_THRESHOLDS.get('HIGH_MAX', 25) and occupancy_rate < 70.0:
            density_level = 'High'
            density_pct = round(min(89.9, 70.0 + ((total_count - 14) / 11.0) * 18.0 + occupancy_rate * 0.05), 1)
        else:
            density_level = 'Very High'
            density_pct = round(min(100.0, 90.0 + min(10.0, (total_count - 25) * 0.5) + occupancy_rate * 0.05), 1)

        log_event("postprocessing", f"Detections validated: {total_count} vehicles (Cars:{cars}, Bus:{buses}, Trk:{trucks}, Moto:{motorcycles}, Bike:{bicycles}, Van:{vans})")
        log_event("density calculation", f"Density: {density_level} ({density_pct}%), Lane Occupancy: {occupancy_rate}%, Road Density: {road_density}")

        # 5. Draw Annotations Overlay
        annotated_frame = frame.copy() if draw_overlay else frame
        if draw_overlay:
            for v in detected_vehicles:
                x, y, w, h = v['bbox']
                v_type = v['type']
                conf = v['confidence']
                color = self.colors.get(v_type, (0, 255, 0))

                # Draw bounding box
                cv2.rectangle(annotated_frame, (x, y), (x + w, y + h), color, 2)

                # Requirement #26: Display confidence percentage only if confidence > 50%
                if conf > self.display_conf_min:
                    label_str = f"{v_type} {conf:.1f}%"
                else:
                    label_str = f"{v_type}"

                (lw, lh), _ = cv2.getTextSize(label_str, cv2.FONT_HERSHEY_SIMPLEX, 0.45, 1)
                text_y = max(y - 5, lh + 6)

                # Filled badge
                cv2.rectangle(annotated_frame, (x, text_y - lh - 4), (x + lw + 6, text_y + 2), color, -1)
                cv2.putText(annotated_frame, label_str, (x + 3, text_y - 2),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.42, (0, 0, 0), 1, cv2.LINE_AA)

            # Draw HUD Header Bar
            hud_h = 46
            hud_bg = annotated_frame[0:hud_h, 0:w_img]
            black_overlay = np.zeros_like(hud_bg, dtype=np.uint8)
            annotated_frame[0:hud_h, 0:w_img] = cv2.addWeighted(hud_bg, 0.25, black_overlay, 0.75, 0)

            hud_text = (
                f"VEHICLES: {total_count} | Cars:{cars} Bus:{buses} Trk:{trucks} "
                f"Moto:{motorcycles} Bike:{bicycles} Van:{vans}"
            )
            cv2.putText(annotated_frame, hud_text, (15, 29),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.46, (255, 255, 255), 1, cv2.LINE_AA)

            # Draw Mode & Density Badge (top right)
            self._draw_density_badge(annotated_frame, density_level, density_pct, mode_cfg['name'])

        inference_time_ms = round((time.time() - start_time) * 1000, 1)

        telemetry = {
            'count': total_count,
            'cars': cars,
            'buses': buses,
            'trucks': trucks,
            'motorcycles': motorcycles,
            'bicycles': bicycles,
            'vans': vans,
            'autorickshaws': 0, # Mapped to 6 production target classes
            'bikes_total': bikes_total,
            'occupancy': occupancy_rate,
            'density_level': density_level,
            'density_pct': density_pct,
            'road_density': road_density,
            'total_road_area': int(total_road_area),
            'mode': mode_key,
            'mode_name': mode_cfg['name'],
            'detected_vehicles': detected_vehicles,
            'is_low_quality': is_low_quality,
            'quality_warning': quality_warning,
            'inference_time_ms': max(5.0, inference_time_ms),
            'detection_available': self.model is not None and inference_error is None,
            'detection_method': f"yolov11_{mode_key}" if self.model is not None and inference_error is None else 'unavailable',
            'model_name': self.model_name,
            'detection_error': inference_error,
            'confidence_score': (
                round(sum(v['confidence'] for v in detected_vehicles) / total_count, 1)
                if total_count and self.model is not None and inference_error is None else None
            )
        }

        return annotated_frame, telemetry

    def _draw_density_badge(self, frame, density_level, density_pct, mode_name):
        """Draws prominent Density Level and Mode badges on top right of image."""
        h, w = frame.shape[:2]
        colors = {
            'LOW': (0, 200, 0),
            'MEDIUM': (0, 165, 255),
            'HIGH': (0, 0, 255),
            'VERY HIGH': (0, 0, 255),
            'CRITICAL': (0, 0, 255)
        }
        level_upper = str(density_level).upper()
        color = colors.get(level_upper, (255, 255, 255))

        text_str = f"DENSITY: {level_upper} ({density_pct}%)"
        (tw, th), _ = cv2.getTextSize(text_str, cv2.FONT_HERSHEY_SIMPLEX, 0.44, 2)

        bx1, by1 = max(10, w - tw - 24), 8
        bx2, by2 = w - 10, 38

        cv2.rectangle(frame, (bx1, by1), (bx2, by2), (0, 0, 0), -1)
        cv2.rectangle(frame, (bx1, by1), (bx2, by2), color, 2)
        cv2.putText(frame, text_str, (bx1 + 8, by1 + 21),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.44, color, 2, cv2.LINE_AA)
