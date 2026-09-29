"""Autoencoder scoring service.

If a trained model bundle exists in model_artifacts/, it is used.
Otherwise an explicitly-labelled synthetic demo model is trained for a UI demo.
Never use demo mode to make real financial decisions.
"""
from pathlib import Path
import os
import numpy as np

FEATURES = [
    "distance_from_home", "distance_from_last_transaction",
    "ratio_to_median_purchase_price", "repeat_retailer",
    "used_chip", "used_pin_number", "online_order",
]
ARTIFACTS = Path(__file__).resolve().parent.parent / "model_artifacts"
_model = None
_scaler = None
_threshold = None
_mode = None

def _load_or_make_demo():
    global _model, _scaler, _threshold, _mode
    if _model is not None:
        return
    model_path = ARTIFACTS / "autoencoder.keras"
    scaler_path = ARTIFACTS / "scaler.npz"
    threshold_path = ARTIFACTS / "threshold.txt"
    if model_path.exists() and scaler_path.exists() and threshold_path.exists():
        import tensorflow as tf
        _model = tf.keras.models.load_model(model_path, compile=False)
        packed = np.load(scaler_path)
        _scaler = (packed["mean"], packed["scale"])
        _threshold = float(threshold_path.read_text().strip())
        _mode = "trained model"
        return

    # Synthetic normal-pattern demo data only; not a model trained on real card transactions.
    from sklearn.preprocessing import StandardScaler
    import tensorflow as tf
    rng = np.random.default_rng(41)
    n = 4500
    normal = np.column_stack([
        rng.lognormal(2.0, .75, n),          # distance from home
        rng.lognormal(0.0, .8, n),           # distance from last transaction
        rng.lognormal(0.0, .45, n),          # purchase price ratio
        rng.binomial(1, .88, n),
        rng.binomial(1, .35, n),
        rng.binomial(1, .25, n),
        rng.binomial(1, .42, n),
    ]).astype("float32")
    scaler = StandardScaler()
    scaled = scaler.fit_transform(normal).astype("float32")
    inp = tf.keras.Input(shape=(len(FEATURES),))
    x = tf.keras.layers.Dense(16, activation="relu")(inp)
    x = tf.keras.layers.Dense(6, activation="relu")(x)
    x = tf.keras.layers.Dense(2, activation="relu")(x)
    x = tf.keras.layers.Dense(6, activation="relu")(x)
    x = tf.keras.layers.Dense(16, activation="relu")(x)
    out = tf.keras.layers.Dense(len(FEATURES), activation="linear")(x)
    model = tf.keras.Model(inp, out)
    model.compile(optimizer="adam", loss="mae")
    model.fit(scaled, scaled, epochs=5, batch_size=128, validation_split=.1, verbose=0)
    errors = np.mean(np.abs(model.predict(scaled, verbose=0) - scaled), axis=1)
    _model, _scaler = model, (scaler.mean_, scaler.scale_)
    _threshold = float(np.quantile(errors, .97))
    _mode = "synthetic demo"
    return

def score_transaction(values):
    _load_or_make_demo()
    raw = np.array([[float(values[name]) for name in FEATURES]], dtype="float32")
    mean, scale = _scaler
    scaled = (raw - mean) / np.where(scale == 0, 1, scale)
    reconstructed = _model.predict(scaled, verbose=0)
    error = float(np.mean(np.abs(reconstructed - scaled)))
    return {
        "error": error,
        "threshold": float(_threshold),
        "flagged": error > _threshold,
        "mode": _mode,
        "features": FEATURES,
    }
