"""Train a deployable TensorFlow autoencoder from card_transdata.csv.

Usage:
  python train_model.py --data card_transdata.csv
  python train_model.py --data card_transdata.csv --mlflow     # also log everything to MLflow

The CSV must contain the seven feature columns and a ``fraud`` target. The scaler and the
threshold are learned from genuine (fraud == 0) rows only. A separate held-out set of
genuine rows plus labelled fraud rows is used for evaluation, so the reported metrics are
not computed on the data that chose the threshold.

With --mlflow the run records: parameters, dataset statistics, per-epoch loss/val_loss
(live), validation-error percentiles, the threshold, held-out ROC-AUC / precision / recall /
F1 / confusion counts, and the artifacts (autoencoder.keras, scaler.npz, threshold.txt,
history and evaluation JSON). Needs MLFLOW_TRACKING_URI (and MLFLOW_TRACKING_USERNAME /
MLFLOW_TRACKING_PASSWORD if the server has login). MLflow problems never abort training.
"""
import argparse
import logging
import os
import platform
import time
from contextlib import nullcontext
from pathlib import Path

import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.metrics import average_precision_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

from detector.observability import apply_client_timeouts, probe_tracking_server, redact_uri
from detector.services import FEATURES

logger = logging.getLogger("train_model")
LAYERS = (64, 16, 2, 16, 64)


class Tracker:
    """Best-effort MLflow wrapper. Disabled tracker = no-ops, so training code has no branches."""

    def __init__(self, mlflow_module=None):
        self.mlflow = mlflow_module

    @property
    def enabled(self):
        return self.mlflow is not None

    def run(self, name):
        return self.mlflow.start_run(run_name=name) if self.enabled else nullcontext()

    def _call(self, label, func, *args, **kwargs):
        if not self.enabled:
            return
        try:
            func(*args, **kwargs)
        except Exception:
            logger.exception("mlflow_%s_failed", label)

    def params(self, values):
        self._call("log_params", lambda: self.mlflow.log_params({k: str(v)[:250] for k, v in values.items()}))

    def metrics(self, values, step=None):
        clean = {}
        for key, value in values.items():
            number = float(value)
            if np.isfinite(number):
                clean[key] = number
        self._call("log_metrics", lambda: self.mlflow.log_metrics(clean, step=step))

    def tags(self, values):
        self._call("set_tags", lambda: self.mlflow.set_tags(values))

    def as_json(self, data, artifact_file):
        self._call("log_dict", lambda: self.mlflow.log_dict(data, artifact_file))

    def file(self, path, artifact_path):
        self._call("log_artifact", lambda: self.mlflow.log_artifact(str(path), artifact_path=artifact_path))


def start_tracker(args):
    uri = os.environ.get("MLFLOW_TRACKING_URI", "").strip()
    if not uri:
        raise SystemExit("--mlflow needs MLFLOW_TRACKING_URI (e.g. https://your-mlflow.onrender.com).")
    apply_client_timeouts()
    try:
        probe_tracking_server(uri)
    except RuntimeError as exc:
        raise SystemExit(f"MLflow is not usable: {exc}")
    try:
        import mlflow
    except ImportError:
        raise SystemExit("Install MLflow first: pip install -r requirements-observability.txt")
    mlflow.set_tracking_uri(uri)
    experiment = args.experiment or os.environ.get("MLFLOW_TRAINING_EXPERIMENT_NAME", "fraud-detection-training")
    mlflow.set_experiment(experiment)
    logger.info("mlflow_training_enabled uri=%s experiment=%s", redact_uri(uri), experiment)
    return Tracker(mlflow)


class EpochLogger(tf.keras.callbacks.Callback):
    """Send loss/val_loss to MLflow after every epoch so the chart updates live."""

    def __init__(self, tracker):
        super().__init__()
        self.tracker = tracker

    def on_epoch_end(self, epoch, logs=None):
        self.tracker.metrics(dict(logs or {}), step=epoch)


def reconstruction_error(model, scaled):
    return np.mean(np.abs(model.predict(scaled, verbose=0) - scaled), axis=1)


def evaluate_holdout(model, scaler, threshold, normal_test, fraud_rows, cap):
    """Labelled evaluation on rows that were never used for fitting or for the threshold."""
    normal_test = normal_test.sample(min(len(normal_test), cap), random_state=1)
    fraud_rows = fraud_rows.sample(min(len(fraud_rows), cap), random_state=1)
    frame = pd.concat([normal_test, fraud_rows])
    y_true = np.concatenate([np.zeros(len(normal_test)), np.ones(len(fraud_rows))]).astype(int)
    scores = reconstruction_error(model, scaler.transform(frame).astype("float32"))
    y_pred = (scores > threshold).astype(int)
    tp = int(((y_pred == 1) & (y_true == 1)).sum())
    fp = int(((y_pred == 1) & (y_true == 0)).sum())
    tn = int(((y_pred == 0) & (y_true == 0)).sum())
    fn = int(((y_pred == 0) & (y_true == 1)).sum())
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {
        "eval_roc_auc": float(roc_auc_score(y_true, scores)),
        "eval_average_precision": float(average_precision_score(y_true, scores)),
        "eval_precision": precision, "eval_recall": recall, "eval_f1": f1,
        "eval_false_positive_rate": fp / (fp + tn) if (fp + tn) else 0.0,
        "eval_true_positives": tp, "eval_false_positives": fp,
        "eval_true_negatives": tn, "eval_false_negatives": fn,
        "eval_normal_rows": len(normal_test), "eval_fraud_rows": len(fraud_rows),
    }


def train(args, tracker):
    df = pd.read_csv(args.data)
    missing = set(FEATURES + ["fraud"]) - set(df.columns)
    if missing:
        raise SystemExit(f"CSV is missing columns: {sorted(missing)}")
    normal = df.loc[df["fraud"] == 0, FEATURES].astype("float32")
    fraud_rows = df.loc[df["fraud"] == 1, FEATURES].astype("float32")
    normal_rest, normal_test = train_test_split(normal, test_size=0.10, random_state=7)
    train_rows, validation = train_test_split(normal_rest, test_size=0.15, random_state=42)

    tracker.params({
        "data_file": Path(args.data).name, "epochs_max": args.epochs, "batch_size": 256,
        "optimizer": "adam", "loss": "mae", "layers": "-".join(map(str, LAYERS)),
        "threshold_quantile": 0.97, "feature_names": ",".join(FEATURES),
        "tensorflow": tf.__version__, "python": platform.python_version(),
    })
    tracker.metrics({
        "rows_total": len(df), "rows_normal": len(normal), "rows_fraud": len(fraud_rows),
        "fraud_rate": len(fraud_rows) / max(len(df), 1),
        "rows_train": len(train_rows), "rows_validation": len(validation), "rows_heldout_normal": len(normal_test),
    })

    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train_rows).astype("float32")
    val_scaled = scaler.transform(validation).astype("float32")

    inp = tf.keras.Input(shape=(len(FEATURES),))
    x = tf.keras.layers.Dense(LAYERS[0], activation="relu")(inp)
    x = tf.keras.layers.Dense(LAYERS[1], activation="relu")(x)
    code = tf.keras.layers.Dense(LAYERS[2], activation="relu")(x)
    x = tf.keras.layers.Dense(LAYERS[3], activation="relu")(code)
    x = tf.keras.layers.Dense(LAYERS[4], activation="relu")(x)
    out = tf.keras.layers.Dense(len(FEATURES), activation="linear")(x)
    model = tf.keras.Model(inp, out, name="transaction_anomaly_autoencoder")
    model.compile(optimizer="adam", loss="mae")
    callbacks = [tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=4, restore_best_weights=True)]
    if tracker.enabled:
        callbacks.append(EpochLogger(tracker))

    started = time.time()
    history = model.fit(train_scaled, train_scaled, validation_data=(val_scaled, val_scaled),
                        epochs=args.epochs, batch_size=256, callbacks=callbacks, verbose=1)
    val_errors = reconstruction_error(model, val_scaled)
    threshold = float(np.quantile(val_errors, 0.97))

    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    model.save(outdir / "autoencoder.keras")
    np.savez(outdir / "scaler.npz", mean=scaler.mean_, scale=scaler.scale_)
    (outdir / "threshold.txt").write_text(str(threshold))
    print(f"Saved model artifacts to {outdir}; threshold={threshold:.6f}")

    history_dict = {k: [float(v) for v in vals] for k, vals in history.history.items()}
    tracker.metrics({
        "threshold": threshold, "epochs_run": len(history_dict.get("loss", [])),
        "best_val_loss": min(history_dict.get("val_loss", [float("nan")])),
        "training_seconds": time.time() - started,
        "val_error_mean": float(val_errors.mean()), "val_error_p50": float(np.quantile(val_errors, 0.50)),
        "val_error_p95": float(np.quantile(val_errors, 0.95)), "val_error_p99": float(np.quantile(val_errors, 0.99)),
        "val_error_max": float(val_errors.max()),
    })
    counts, edges = np.histogram(val_errors, bins=20)
    tracker.as_json(history_dict, "training/history.json")
    tracker.as_json({"bin_edges": edges.tolist(), "counts": counts.tolist()}, "evaluation/validation_error_histogram.json")

    evaluation = None
    if len(fraud_rows) and len(normal_test):
        try:
            evaluation = evaluate_holdout(model, scaler, threshold, normal_test, fraud_rows, args.eval_max_rows)
            tracker.metrics(evaluation)
            tracker.as_json(evaluation, "evaluation/holdout_metrics.json")
            print("Held-out evaluation:", {k: round(v, 4) if isinstance(v, float) else v for k, v in evaluation.items()})
        except Exception:
            logger.exception("holdout_evaluation_failed")
    else:
        logger.warning("holdout_evaluation_skipped reason=no_fraud_or_no_heldout_rows")

    for name in ("autoencoder.keras", "scaler.npz", "threshold.txt"):
        tracker.file(outdir / name, "model_bundle")
    tracker.tags({"stage": "training", "has_holdout_eval": str(evaluation is not None)})


def main():
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to card_transdata.csv")
    parser.add_argument("--output", default="model_artifacts")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--mlflow", action="store_true", help="Log this training run to MLflow")
    parser.add_argument("--experiment", default=None, help="MLflow experiment (default: fraud-detection-training)")
    parser.add_argument("--eval-max-rows", type=int, default=100000, help="Max rows per class for held-out evaluation")
    args = parser.parse_args()

    tracker = start_tracker(args) if args.mlflow else Tracker()
    with tracker.run(f"train-{time.strftime('%Y%m%d-%H%M%S')}"):
        try:
            train(args, tracker)
        except BaseException:
            logger.exception("training_failed")  # MLflow marks the run FAILED when this re-raises
            raise


if __name__ == "__main__":
    main()
