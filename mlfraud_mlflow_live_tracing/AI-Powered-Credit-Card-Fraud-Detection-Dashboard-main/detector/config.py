"""Runtime configuration for the demo scorer."""
import os


def get_demo_threshold() -> float:
    """Read a threshold in [0, 1], validating deployment configuration."""
    raw = os.environ.get("DEMO_ANOMALY_THRESHOLD", "0.50")
    try:
        threshold = float(raw)
    except ValueError as exc:
        raise ValueError("DEMO_ANOMALY_THRESHOLD must be a number between 0 and 1.") from exc
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("DEMO_ANOMALY_THRESHOLD must be between 0 and 1.")
    return threshold
