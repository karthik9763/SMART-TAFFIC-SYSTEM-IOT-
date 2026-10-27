import sys
import os

print("=" * 65)
print("  SMART TRAFFIC DENSITY PREDICTION USING IOT & DNN  ")
print("  B.E. Final Year Computer Science Thesis Project   ")
print("=" * 65)

# Check trained model
model_path = os.path.join("ml", "models", "traffic_dnn_model.pkl")
if not os.path.exists(model_path):
    print("[Initializer] Training DNN model for the first time...")
    try:
        from ml.train_density_model import train_and_evaluate_dnn
        train_and_evaluate_dnn()
    except Exception as e:
        print(f"[Initializer Warning] Could not train model automatically: {e}")

# Import and launch Flask with Socket.IO
from app import app, init_db, socketio

if __name__ == '__main__':
    with app.app_context():
        init_db(app)
    print("\n[Server Ready] Access the Smart Traffic Web Dashboard at:")
    print("  -> http://127.0.0.1:5000\n")
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
