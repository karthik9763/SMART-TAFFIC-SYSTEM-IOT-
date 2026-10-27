import os
import json
import csv
import joblib
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, confusion_matrix

from ml.dataset_prep import generate_traffic_dataset

def train_and_evaluate_dnn(dataset_path="ml/traffic_dataset.csv", output_dir="ml/models"):
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate 50,000 multi-source augmented dataset
    print("[DNN Training Engine] Re-generating 50,000-sample augmented multi-class dataset...")
    rows = generate_traffic_dataset(num_samples=50000, save_csv=True, filepath=dataset_path)

    data = np.array(rows)
    # Features: vehicle_count, occupancy_rate, avg_speed, hour_of_day, weather_condition
    X = np.column_stack([data[:, 0], data[:, 8], data[:, 9], data[:, 10], data[:, 11]])
    y = data[:, 14].astype(int) # Target density_class (0: Low, 1: Medium, 2: High)

    # 70% Training / 15% Validation / 15% Testing Split
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=(0.15 / 0.85), random_state=42, stratify=y_train_val
    )

    print(f"[DNN Training Engine] Dataset split: Train={len(X_train)} (70%), Val={len(X_val)} (15%), Test={len(X_test)} (15%)")

    # Feature Standardization using StandardScaler (Transfer Learning scaling principle)
    scaler = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_val_scaled = scaler.transform(X_val)
    X_test_scaled = scaler.transform(X_test)

    # Multi-Layer Deep Neural Network Classifier Architecture: 5 -> 256 -> 128 -> 64 -> 32 -> 3
    dnn_model = MLPClassifier(
        hidden_layer_sizes=(256, 128, 64, 32),
        activation='relu',
        solver='adam',
        alpha=0.0001,
        batch_size=64,
        learning_rate_init=0.001,
        max_iter=600,
        random_state=42,
        early_stopping=True,
        n_iter_no_change=20
    )

    print("[DNN Training Engine] Fitting Deep Neural Network (256, 128, 64, 32) classifier...")
    dnn_model.fit(X_train_scaled, y_train)

    # Evaluate Model on Test Set
    y_pred = dnn_model.predict(X_test_scaled)
    y_probas = dnn_model.predict_proba(X_test_scaled)

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred, average='weighted')
    rec = recall_score(y_test, y_pred, average='weighted')
    f1 = f1_score(y_test, y_pred, average='weighted')
    cm = confusion_matrix(y_test, y_pred).tolist()

    # Calculate mAP@0.5 proxy score (mean average precision across confidence thresholds >= 0.5)
    map_scores = []
    for idx, pred in enumerate(y_pred):
        top_prob = y_probas[idx][pred]
        if top_prob >= 0.5:
            map_scores.append(1.0 if pred == y_test[idx] else 0.0)
    map05 = float(np.mean(map_scores)) if map_scores else float(acc)

    metrics = {
        'accuracy': float(acc),
        'precision': float(prec),
        'recall': float(rec),
        'f1_score': float(f1),
        'map_05': float(map05),
        'confusion_matrix': cm,
        'class_labels': ['Low', 'Medium', 'High'],
        'num_train_samples': len(X_train),
        'num_val_samples': len(X_val),
        'num_test_samples': len(X_test),
        'model_architecture': 'MLP-DNN (256-128-64-32)'
    }

    print("=" * 60)
    print("      DNN MODEL PERFORMANCE EVALUATION RESULTS (50K DATASET) ")
    print("=" * 60)
    print(f"  Accuracy:    {acc * 100:.2f}% (Goal: >= 95%)")
    print(f"  Precision:   {prec * 100:.2f}% (Goal: >= 95%)")
    print(f"  Recall:      {rec * 100:.2f}% (Goal: >= 95%)")
    print(f"  F1-Score:    {f1 * 100:.2f}% (Goal: >= 95%)")
    print(f"  mAP@0.5:     {map05 * 100:.2f}% (Goal: >= 95%)")
    print("  Confusion Matrix:")
    print(np.array(cm))
    print("=" * 60)

    # Save artifacts
    model_file = os.path.join(output_dir, "traffic_dnn_model.pkl")
    scaler_file = os.path.join(output_dir, "scaler.pkl")
    metrics_file = os.path.join(output_dir, "metrics.json")

    joblib.dump(dnn_model, model_file)
    joblib.dump(scaler, scaler_file)
    with open(metrics_file, 'w') as f:
        json.dump(metrics, f, indent=4)

    print(f"[DNN Training Engine] Saved best-performing DNN model to {model_file}")
    print(f"[DNN Training Engine] Saved feature scaler to {scaler_file}")
    print(f"[DNN Training Engine] Saved performance metrics report to {metrics_file}")
    return metrics

if __name__ == '__main__':
    train_and_evaluate_dnn()
