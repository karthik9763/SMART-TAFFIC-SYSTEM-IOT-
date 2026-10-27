import os
import sys
import json
import random
from collections import Counter
from pathlib import Path
from huggingface_hub import snapshot_download

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "ua_detrac"
MODELS_DIR = BASE_DIR / "ml" / "models"

# Hugging Face or public repository fallback for UA-DETRAC benchmark
DATASET_REPO = "SmartTraffic/UA-DETRAC"

def download_ua_detrac():
    """
    Downloads or references the UA-DETRAC dataset and XML annotations.
    Dataset directory structure:
    data/ua_detrac/
       ├── DETRAC-train-data/       (Image sequence folders: MVI_20011, MVI_20012, etc.)
       ├── DETRAC-Train-Annotations-XML/ (Per-sequence XML files: MVI_20011.xml, etc.)
       └── converted_labels/        (YOLO format normalized .txt labels)
    """
    print("=" * 70)
    print("      UA-DETRAC DATASET ACQUISITION & SEQUENCE PARSER ENGINE      ")
    print("=" * 70)
    print(f"[Dataset Engine] Target directory: {DATA_DIR}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Download / Sync UA-DETRAC Repository Files
    print(f"\n[Dataset Engine] Syncing UA-DETRAC dataset repository: {DATASET_REPO}...")
    try:
        dataset_path = snapshot_download(
            repo_id=DATASET_REPO,
            repo_type="dataset",
            local_dir=str(DATA_DIR),
            local_dir_use_symlinks=False,
            resume_download=True
        )
        print(f"[Dataset Engine] UA-DETRAC dataset synced to: {dataset_path}")
    except Exception as e:
        print(f"[Dataset Engine Notice] Direct repository download notice: {e}")
        print("[Dataset Engine] Using local directory structure for UA-DETRAC image sequences & XMLs.")

    # 2. Compute Sequence Statistics
    sequence_dirs = [d for d in DATA_DIR.rglob("MVI_*") if d.is_dir()]
    xml_files = list(DATA_DIR.rglob("*.xml"))

    print("\n" + "=" * 70)
    print("               UA-DETRAC DATASET SUMMARY REPORT                ")
    print("=" * 70)
    print(f"  Total Video Sequences Found: {len(sequence_dirs)}")
    print(f"  Total XML Annotation Files: {len(xml_files)}")
    print("=" * 70)

    stats_file = DATA_DIR / "dataset_stats.json"
    stats_data = {
        "dataset_name": "UA-DETRAC Benchmark",
        "total_sequences": len(sequence_dirs),
        "total_xml_files": len(xml_files),
        "dataset_path": str(DATA_DIR)
    }

    with open(stats_file, 'w', encoding='utf-8') as f:
        json.dump(stats_data, f, indent=4)

    return stats_data

if __name__ == '__main__':
    download_ua_detrac()
