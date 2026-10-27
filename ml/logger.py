import os
import logging
from pathlib import Path
from datetime import datetime

LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
INFERENCE_LOG_FILE = LOGS_DIR / "inference.log"

# Dedicated logger for production inference tracking
inference_logger = logging.getLogger("smarttraffic.inference")
inference_logger.setLevel(logging.INFO)

# File handler
_file_handler = logging.FileHandler(str(INFERENCE_LOG_FILE), encoding="utf-8")
_file_formatter = logging.Formatter(
    "[%(asctime)s] [%(levelname)s] [InferenceEngine] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
_file_handler.setFormatter(_file_formatter)

# Console handler
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_file_formatter)

if not inference_logger.handlers:
    inference_logger.addHandler(_file_handler)
    inference_logger.addHandler(_console_handler)

def log_event(stage, details=""):
    """
    Standardized production event logging:
    Stages: model loaded, image received, preprocessing, inference,
            postprocessing, density calculation, dashboard update, API response
    """
    msg = f"Stage: [{stage}]"
    if details:
        msg += f" - {details}"
    inference_logger.info(msg)
