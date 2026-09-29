
"""Lightweight anomaly scoring for the demo dashboard.

This is a heuristic demo, NOT a trained fraud detection model.
Do not use it for real financial decisions.
"""
import numpy as np

FEATURES = [
    "distance_from_home",
    "distance_from_last_transaction",
    "ratio_to_median_purchase_price",
    "repeat_retailer",
    "used_chip",
    "used_pin_number",
    "online_order",
]


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
