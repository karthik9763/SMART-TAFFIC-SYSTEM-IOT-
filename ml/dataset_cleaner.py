import os
import hashlib
import shutil
import random
from pathlib import Path
from collections import Counter, defaultdict
import cv2
import numpy as np

from ml.config import TARGET_CLASSES, DATASET_DIR, ML_DIR, BASE_DIR

random.seed(42)

def compute_image_md5(file_path):
    """Computes MD5 hash of an image file to detect duplicates."""
    hash_md5 = hashlib.md5()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        return hash_md5.hexdigest()
    except Exception:
        return None

def verify_and_clean_image(img_path):
    """Verifies image file readability and dimensions."""
    if not img_path.exists() or img_path.stat().st_size == 0:
        return False, 0, 0, 0
    try:
        img = cv2.imread(str(img_path))
        if img is None or img.size == 0:
            return False, 0, 0, 0
        h, w, c = img.shape
        if h < 10 or w < 10:
            return False, 0, 0, 0
        return True, w, h, c
    except Exception:
        return False, 0, 0, 0

def clean_and_verify_annotation(label_path, num_classes=len(TARGET_CLASSES)):
    """Verifies and cleans YOLO bounding box lines."""
    if not label_path.exists():
        return []

    valid_lines = []
    try:
        with open(label_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for line in lines:
            parts = line.strip().split()
            if len(parts) < 5:
                continue
            try:
                cls_id = int(float(parts[0]))
                xc, yc, w, h = [float(p) for p in parts[1:5]]

                if cls_id < 0 or cls_id >= num_classes:
                    continue
                if not (0.0 <= xc <= 1.0 and 0.0 <= yc <= 1.0):
                    continue
                if w <= 0.001 or h <= 0.001 or w > 1.0 or h > 1.0:
                    continue

                xc = round(max(0.0001, min(0.9999, xc)), 6)
                yc = round(max(0.0001, min(0.9999, yc)), 6)
                w = round(max(0.0001, min(1.0, w)), 6)
                h = round(max(0.0001, min(1.0, h)), 6)

                valid_lines.append(f"{cls_id} {xc} {yc} {w} {h}")
            except (ValueError, TypeError):
                continue
    except Exception:
        pass

    return valid_lines

def extract_sequence_id(file_path):
    """
    Extracts UA-DETRAC sequence ID (e.g. MVI_20011) from image/label filename or parent directory.
    Prevents frame leakage between train/val/test splits.
    """
    stem = file_path.stem
    parts = stem.split('_')
    for p in parts:
        if p.startswith("MVI"):
            return p
        if p.isdigit() and len(p) == 5:
            return f"MVI_{p}"

    parent_name = file_path.parent.name
    if parent_name.startswith("MVI"):
        return parent_name

    return "MVI_DEFAULT"

def prepare_and_clean_dataset(source_images_dir=None, source_labels_dir=None, output_yolo_dir=DATASET_DIR):
    """
    Performs full UA-DETRAC dataset cleaning and SEQUENCE-BASED 70/20/10 split.
    Groups frames by sequence name (e.g. MVI_20011) to eliminate frame leakage across splits.
    Generates data.yaml for YOLO training.
    """
    print("=" * 75)
    print("      UA-DETRAC SEQUENCE-BASED CLEANING & STRATIFIED SPLIT ENGINE      ")
    print("=" * 75)

    output_yolo_dir = Path(output_yolo_dir)
    train_img_dir = output_yolo_dir / "train" / "images"
    train_lbl_dir = output_yolo_dir / "train" / "labels"
    val_img_dir = output_yolo_dir / "val" / "images"
    val_lbl_dir = output_yolo_dir / "val" / "labels"
    test_img_dir = output_yolo_dir / "test" / "images"
    test_lbl_dir = output_yolo_dir / "test" / "labels"

    for d in [train_img_dir, train_lbl_dir, val_img_dir, val_lbl_dir, test_img_dir, test_lbl_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # Search directories for images
    image_candidates = []
    search_dirs = [DATASET_DIR, BASE_DIR / "data"]
    if source_images_dir and Path(source_images_dir).exists():
        search_dirs.insert(0, Path(source_images_dir))

    for s_dir in search_dirs:
        if s_dir.exists():
            for ext in ["*.jpg", "*.png", "*.jpeg", "*.JPG", "*.PNG", "*.JPEG"]:
                image_candidates.extend(list(s_dir.rglob(ext)))

    print(f"[Dataset Cleaner] Found {len(image_candidates)} candidate image files.")

    seen_hashes = set()
    sequence_map = defaultdict(list)
    total_cleaned_bboxes = 0
    class_distribution = Counter()

    for img_p in image_candidates:
        img_hash = compute_image_md5(img_p)
        if not img_hash or img_hash in seen_hashes:
            continue

        is_valid, w, h, c = verify_and_clean_image(img_p)
        if not is_valid:
            continue

        # Look for matching .txt label in converted_labels or parallel directory
        lbl_p = img_p.with_suffix(".txt")
        if not lbl_p.exists():
            alt_lbl_p = DATASET_DIR / "converted_labels" / f"{img_p.stem}.txt"
            if alt_lbl_p.exists():
                lbl_p = alt_lbl_p

        cleaned_bboxes = clean_and_verify_annotation(lbl_p) if lbl_p.exists() else []
        if not cleaned_bboxes:
            continue

        seen_hashes.add(img_hash)
        seq_id = extract_sequence_id(img_p)
        sequence_map[seq_id].append((img_p, cleaned_bboxes))

        for bbox_line in cleaned_bboxes:
            cls_id = int(bbox_line.split()[0])
            class_distribution[cls_id] += 1
            total_cleaned_bboxes += 1

    unique_sequences = list(sequence_map.keys())
    print(f"[Dataset Cleaner] Grouped frames into {len(unique_sequences)} distinct video sequences.")
    print(f"[Dataset Cleaner] Total valid frames: {sum(len(v) for v in sequence_map.values())}")
    print(f"[Dataset Cleaner] Total verified bounding boxes: {total_cleaned_bboxes}")

    # Sequence-Based Split: 70% Train / 20% Val / 10% Test
    random.shuffle(unique_sequences)
    n_seq = len(unique_sequences)

    n_train_seq = int(n_seq * 0.70)
    n_val_seq = int(n_seq * 0.20)

    train_seqs = set(unique_sequences[:n_train_seq])
    val_seqs = set(unique_sequences[n_train_seq:n_train_seq + n_val_seq])
    test_seqs = set(unique_sequences[n_train_seq + n_val_seq:])

    print(f"\n[Dataset Cleaner] Sequence-Based Split (No Frame Leakage):")
    print(f"  - Training Sequences (70%):   {len(train_seqs)} video sequences")
    print(f"  - Validation Sequences (20%): {len(val_seqs)} video sequences")
    print(f"  - Testing Sequences (10%):    {len(test_seqs)} video sequences")

    def write_sequence_split(seq_set, target_img_dir, target_lbl_dir):
        count = 0
        for seq_id in seq_set:
            for idx, (img_p, bboxes) in enumerate(sequence_map[seq_id]):
                dest_img_name = f"{seq_id}_{idx:05d}{img_p.suffix.lower()}"
                dest_lbl_name = f"{seq_id}_{idx:05d}.txt"

                shutil.copy2(img_p, target_img_dir / dest_img_name)
                with open(target_lbl_dir / dest_lbl_name, 'w', encoding='utf-8') as f:
                    f.write("\n".join(bboxes) + "\n")
                count += 1
        return count

    write_sequence_split(train_seqs, train_img_dir, train_lbl_dir)
    write_sequence_split(val_seqs, val_img_dir, val_lbl_dir)
    write_sequence_split(test_seqs, test_img_dir, test_lbl_dir)

    # Generate YOLO data.yaml
    data_yaml_content = f"""# YOLOv11 / YOLO Dataset Config for UA-DETRAC Traffic Benchmark
path: {output_yolo_dir.as_posix()}
train: train/images
val: val/images
test: test/images

# Number of Classes
nc: {len(TARGET_CLASSES)}

# Target Class Names
names:
  0: Car
  1: Bus
  2: Truck
  3: Motorcycle
  4: Bicycle
  5: Van
  6: Auto-rickshaw
"""
    yaml_path = output_yolo_dir / "data.yaml"
    with open(yaml_path, 'w', encoding='utf-8') as f:
        f.write(data_yaml_content)

    print(f"\n[Dataset Cleaner] Created YOLO dataset config: {yaml_path}")
    print("=" * 75)
    return yaml_path, len(seen_hashes)

if __name__ == '__main__':
    prepare_and_clean_dataset()
