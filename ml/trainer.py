import os
import sys
import torch
from pathlib import Path
from ultralytics import YOLO

from ml.config import TRAIN_CONFIG, MODELS_DIR, DATASET_DIR
from ml.dataset_cleaner import prepare_and_clean_dataset
from ml.augmentation import get_yolo_augmentation_hyperparams

def train_yolo_model(dataset_yaml=None, custom_epochs=None, model_weights="yolo11n.pt"):
    """
    Trains the YOLO model using transfer learning, mixed precision (AMP),
    Cosine Learning Rate Scheduler, AdamW optimizer, and early stopping.
    Automatically selects CUDA GPU if available.
    """
    print("=" * 75)
    print("      DEEP NEURAL NETWORK (YOLO) VEHICLE DETECTION TRAINING ENGINE      ")
    print("=" * 75)

    # 1. Device Selection (CUDA GPU if available, else CPU)
    if torch.cuda.is_available():
        device_str = "0"
        gpu_name = torch.cuda.get_device_name(0)
        print(f"[Training Engine] GPU Hardware Detected: {gpu_name}")
    else:
        device_str = "cpu"
        print("[Training Engine] Running on CPU (CUDA unavailable).")

    # 2. Check / Prepare Dataset data.yaml
    if dataset_yaml is None or not Path(dataset_yaml).exists():
        dataset_yaml, num_samples = prepare_and_clean_dataset()

    yaml_path = Path(dataset_yaml).resolve()

    # 3. Load Transfer Learning Model Backbone
    print(f"\n[Training Engine] Loading Transfer Learning Backbone Weights: {model_weights}...")
    try:
        model = YOLO(model_weights)
    except Exception as e:
        print(f"[Training Engine Warning] Could not load {model_weights} directly: {e}. Falling back to yolo8n.pt...")
        model = YOLO("yolov8n.pt")

    # 4. Merge Training Configuration & Realistic Augmentation Hyperparameters
    epochs = custom_epochs or TRAIN_CONFIG['epochs']
    aug_params = get_yolo_augmentation_hyperparams()

    print("\n[Training Engine] Training Configuration Parameters:")
    print(f"  - Architecture:              YOLO Transfer Learning Backbone")
    print(f"  - Target Dataset Config:     {yaml_path}")
    print(f"  - Epochs:                    {epochs}")
    print(f"  - Image Resolution (imgsz):  {TRAIN_CONFIG['imgsz']}x{TRAIN_CONFIG['imgsz']}")
    print(f"  - Batch Size:                {TRAIN_CONFIG['batch']} (Auto-batch tuning enabled)")
    print(f"  - Early Stopping Patience:   {TRAIN_CONFIG['patience']} epochs")
    print(f"  - Optimizer:                 {TRAIN_CONFIG['optimizer']}")
    print(f"  - Initial Learning Rate:     {TRAIN_CONFIG['lr0']}")
    print(f"  - Weight Decay:              {TRAIN_CONFIG['weight_decay']}")
    print(f"  - Mixed Precision (AMP):     {TRAIN_CONFIG['amp']}")
    print(f"  - Cosine LR Scheduler:       {TRAIN_CONFIG['cos_lr']}")
    print(f"  - Workers:                   {TRAIN_CONFIG['workers']}")
    print(f"  - Target Device:             {device_str}")
    print("=" * 75)

    # 5. Launch Model Training
    project_dir = MODELS_DIR / "yolo_runs"
    project_dir.mkdir(parents=True, exist_ok=True)

    training_args = {
        'data': str(yaml_path),
        'epochs': epochs,
        'imgsz': TRAIN_CONFIG['imgsz'],
        'batch': TRAIN_CONFIG['batch'],
        'patience': TRAIN_CONFIG['patience'],
        'optimizer': TRAIN_CONFIG['optimizer'],
        'lr0': TRAIN_CONFIG['lr0'],
        'weight_decay': TRAIN_CONFIG['weight_decay'],
        'workers': TRAIN_CONFIG['workers'],
        'cache': TRAIN_CONFIG['cache'],
        'amp': TRAIN_CONFIG['amp'],
        'cos_lr': TRAIN_CONFIG['cos_lr'],
        'device': device_str,
        'project': str(project_dir),
        'name': 'train_results',
        'exist_ok': True,
        'save': True,
        'save_period': -1,
        'plots': True,
        **aug_params
    }

    try:
        results = model.train(**training_args)
        
        # Copy best.pt & last.pt to ml/models/
        run_weights_dir = project_dir / "train_results" / "weights"
        best_ckpt = run_weights_dir / "best.pt"
        last_ckpt = run_weights_dir / "last.pt"

        dest_best = MODELS_DIR / "best.pt"
        dest_last = MODELS_DIR / "last.pt"

        if best_ckpt.exists():
            import shutil
            shutil.copy2(best_ckpt, dest_best)
            print(f"\n[Training Engine SUCCESS] Saved best model checkpoint to: {dest_best}")

        if last_ckpt.exists():
            import shutil
            shutil.copy2(last_ckpt, dest_last)
            print(f"[Training Engine SUCCESS] Saved last model checkpoint to: {dest_last}")

        return model, results
    except Exception as ex:
        print(f"[Training Engine Error] Training execution encountered an exception: {ex}")
        return model, None

if __name__ == '__main__':
    train_yolo_model()
