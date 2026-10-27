import os
import sys
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from ml.dataset_cleaner import prepare_and_clean_dataset
from ml.trainer import train_yolo_model
from ml.evaluator import evaluate_yolo_model

def run_full_training_and_evaluation_pipeline(epochs=200):
    """
    Executes full end-to-end dataset cleaning, training, evaluation, and artifact saving pipeline:
    1. Clean & sanitize dataset (remove duplicates, corrupted images, bad bboxes).
    2. Split 70% Train / 20% Val / 10% Test.
    3. Train YOLO model with transfer learning, AMP, Cosine LR, AdamW, early stopping.
    4. Save best.pt, last.pt, loss curves, confusion matrices, and metrics report.
    """
    print("=" * 80)
    print("      SMART TRAFFIC DETECTOR: FULL TRAINING & EVALUATION PIPELINE      ")
    print("=" * 80)

    # 1. Dataset Cleaning & Stratified 70/20/10 Split
    yaml_path, num_samples = prepare_and_clean_dataset()

    # 2. Model Training with Transfer Learning & Early Stopping
    print(f"\n[Pipeline Engine] Launching YOLO Training on {num_samples} cleaned samples...")
    model, results = train_yolo_model(dataset_yaml=yaml_path, custom_epochs=epochs)

    # 3. Model Performance Evaluation
    print("\n[Pipeline Engine] Evaluating trained model on 10% test split...")
    metrics = evaluate_yolo_model(dataset_yaml=yaml_path)

    print("\n" + "=" * 80)
    print("      FULL PIPELINE EXECUTION COMPLETED SUCCESSFULLY      ")
    print("=" * 80)
    return metrics

if __name__ == '__main__':
    epochs_to_run = 200
    if len(sys.argv) > 1:
        try:
            epochs_to_run = int(sys.argv[1])
        except ValueError:
            pass
    run_full_training_and_evaluation_pipeline(epochs=epochs_to_run)
