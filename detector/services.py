<<<<<<< HEAD
"""Transaction scoring service with lazy optional autoencoder loading.

Without a complete trained artifact bundle, the service uses a transparent,
rule-based heuristic for UI demonstrations. It is not a validated fraud model.
"""
import logging
import os
from pathlib import Path
from threading import Lock

import numpy as np
from .config import get_demo_threshold

logger = logging.getLogger(__name__)
=======

"""Lightweight anomaly scoring for the demo dashboard.

This is a heuristic demo, NOT a trained fraud detection model.
Do not use it for real financial decisions.
"""
import numpy as np

>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
FEATURES = [
    "distance_from_home",
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "repeat_retailer",
    "used_chip",
    "used_pin_number",
    "online_order",
]
<<<<<<< HEAD
BINARY_FEATURES = {"repeat_retailer", "used_chip", "used_pin_number", "online_order"}
ARTIFACTS = Path(os.environ.get(
    "MODEL_ARTIFACTS_DIR", str(Path(__file__).resolve().parent.parent / "model_artifacts")
))
_MODEL = None
_SCALER = None
_MODEL_THRESHOLD = None
_MODEL_LOCK = Lock()


class ScoringError(Exception):
    """Expected, user-safe scoring configuration or inference error."""


def _validated_vector(values) -> np.ndarray:
    missing = [name for name in FEATURES if name not in values]
    if missing:
        raise ValueError(f"Missing required features: {', '.join(missing)}")
    try:
        raw = np.asarray([float(values[name]) for name in FEATURES], dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("All transaction features must be numeric.") from exc
    if not np.isfinite(raw).all():
        raise ValueError("Transaction features must be finite numbers.")
    if (raw[:3] < 0).any():
        raise ValueError("Distance and purchase-ratio features cannot be negative.")
    for index, name in enumerate(FEATURES):
        if name in BINARY_FEATURES and raw[index] not in (0.0, 1.0):
            raise ValueError(f"{name} must be either 0 or 1.")
    return raw.reshape(1, -1).astype("float32")


def _load_trained_bundle_if_present():
    """Load artifacts only when a complete bundle exists; never train on web requests."""
    global _MODEL, _SCALER, _MODEL_THRESHOLD
    model_path = ARTIFACTS / "autoencoder.keras"
    scaler_path = ARTIFACTS / "scaler.npz"
    threshold_path = ARTIFACTS / "threshold.txt"
    present = [path.exists() for path in (model_path, scaler_path, threshold_path)]
    if not any(present):
        return None
    if not all(present):
        raise ScoringError(
            "Model artifact bundle is incomplete. Provide autoencoder.keras, scaler.npz, and threshold.txt."
        )
    if _MODEL is not None:
        return _MODEL, _SCALER, _MODEL_THRESHOLD
    with _MODEL_LOCK:
        if _MODEL is not None:
            return _MODEL, _SCALER, _MODEL_THRESHOLD
        try:
            import tensorflow as tf  # Optional dependency; imported only for a trained model.
            model = tf.keras.models.load_model(model_path, compile=False)
            with np.load(scaler_path, allow_pickle=False) as packed:
                mean = np.asarray(packed["mean"], dtype=np.float32)
                scale = np.asarray(packed["scale"], dtype=np.float32)
            threshold = float(threshold_path.read_text(encoding="utf-8").strip())
            if mean.shape != (len(FEATURES),) or scale.shape != (len(FEATURES),):
                raise ValueError("Scaler shape does not match the seven expected features.")
            if not np.isfinite(mean).all() or not np.isfinite(scale).all() or (scale <= 0).any():
                raise ValueError("Scaler contains invalid values.")
            if not np.isfinite(threshold) or threshold < 0:
                raise ValueError("Model threshold must be a finite non-negative number.")
        except Exception as exc:
            logger.exception("trained_model_load_failed artifact_dir=%s", ARTIFACTS)
            raise ScoringError(
                "The trained model could not be loaded. Check model artifacts and optional ML dependencies."
            ) from exc
        _MODEL, _SCALER, _MODEL_THRESHOLD = model, (mean, scale), threshold
        logger.info("trained_model_loaded artifact_dir=%s", ARTIFACTS)
        return _MODEL, _SCALER, _MODEL_THRESHOLD


def _heuristic_score(raw: np.ndarray) -> float:
    distance_home, distance_last, price_ratio, repeat_retailer, used_chip, used_pin, online_order = raw[0]
    score = 0.0
    score += min(float(distance_home) / 100.0, 1.0) * 0.25
    score += min(float(distance_last) / 50.0, 1.0) * 0.20
    score += min(float(price_ratio) / 5.0, 1.0) * 0.30
    score += (1.0 - float(repeat_retailer)) * 0.10
    score += (1.0 - float(used_chip)) * 0.05
    score += (1.0 - float(used_pin)) * 0.05
    score += float(online_order) * 0.05
    return float(np.clip(score, 0.0, 1.0))


def score_transaction(values) -> dict:
    """Return a normalized score and review flag for validated feature values."""
    raw = _validated_vector(values)
    bundle = _load_trained_bundle_if_present()
    if bundle is not None:
        model, (mean, scale), threshold = bundle
        scaled = (raw - mean) / np.where(scale == 0, 1.0, scale)
        reconstructed = model.predict(scaled, verbose=0)
        score = float(np.mean(np.abs(reconstructed - scaled)))
        mode = "autoencoder"
    else:
        score = _heuristic_score(raw)
        threshold = get_demo_threshold()
        mode = "heuristic_demo"
    if not np.isfinite(score):
        raise ScoringError("Scoring returned a non-finite result.")
    result = {
        "score": score,
        "threshold": float(threshold),
        "flagged": bool(score > threshold),
        "mode": mode,
        "features": FEATURES,
    }
    logger.info("transaction_scored mode=%s flagged=%s score=%.5f", mode, result["flagged"], score)
    return result
=======


def score_transaction(values):
    raw = np.array(
        [[float(values[name]) for name in FEATURES]],
        dtype=float,
    )[0]

    # Simple heuristic risk score for demonstration only.
    distance_home = max(raw[0], 0)
    distance_last = max(raw[1], 0)
    price_ratio = max(raw[2], 0)
    repeat_retailer, used_chip, used_pin, online_order = raw[3:]

    score = 0.0
    score += min(distance_home / 100, 1) * 0.25
    score += min(distance_last / 50, 1) * 0.20
    score += min(price_ratio / 5, 1) * 0.30
    score += (1 - repeat_retailer) * 0.10
    score += (1 - used_chip) * 0.05
    score += (1 - used_pin) * 0.05
    score += online_order * 0.05

    threshold = 0.50

    return {
        "error": float(score),
        "threshold": threshold,
        "flagged": bool(score > threshold),
        "mode": "heuristic demo (not a trained model)",
        "features": FEATURES,
    }
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
