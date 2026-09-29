"""Train a deployable TensorFlow autoencoder from card_transdata.csv.

Usage:
  python train_model.py --data card_transdata.csv
The CSV should contain the seven feature columns and a `fraud` target.
The scaler and threshold are learned from genuine training rows only.
"""
import argparse
from pathlib import Path
import numpy as np
import pandas as pd
import tensorflow as tf
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from detector.services import FEATURES

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, help="Path to card_transdata.csv")
    parser.add_argument("--output", default="model_artifacts")
    parser.add_argument("--epochs", type=int, default=20)
    args = parser.parse_args()
    df = pd.read_csv(args.data)
    missing = set(FEATURES + ["fraud"]) - set(df.columns)
    if missing:
        raise SystemExit(f"CSV is missing columns: {sorted(missing)}")
    normal = df.loc[df["fraud"] == 0, FEATURES].astype("float32")
    train, validation = train_test_split(normal, test_size=.15, random_state=42)
    scaler = StandardScaler()
    train_scaled = scaler.fit_transform(train).astype("float32")
    val_scaled = scaler.transform(validation).astype("float32")
    inp = tf.keras.Input(shape=(len(FEATURES),))
    x = tf.keras.layers.Dense(64, activation="relu")(inp)
    x = tf.keras.layers.Dense(16, activation="relu")(x)
    code = tf.keras.layers.Dense(2, activation="relu")(x)
    x = tf.keras.layers.Dense(16, activation="relu")(code)
    x = tf.keras.layers.Dense(64, activation="relu")(x)
    out = tf.keras.layers.Dense(len(FEATURES), activation="linear")(x)
    model = tf.keras.Model(inp, out, name="transaction_anomaly_autoencoder")
    model.compile(optimizer="adam", loss="mae")
    callbacks = [tf.keras.callbacks.EarlyStopping(
        monitor="val_loss", patience=4, restore_best_weights=True
    )]
    model.fit(train_scaled, train_scaled, validation_data=(val_scaled, val_scaled),
              epochs=args.epochs, batch_size=256, callbacks=callbacks, verbose=1)
    val_errors = np.mean(np.abs(model.predict(val_scaled, verbose=0) - val_scaled), axis=1)
    threshold = float(np.quantile(val_errors, .97))
    outdir = Path(args.output)
    outdir.mkdir(parents=True, exist_ok=True)
    model.save(outdir / "autoencoder.keras")
    np.savez(outdir / "scaler.npz", mean=scaler.mean_, scale=scaler.scale_)
    (outdir / "threshold.txt").write_text(str(threshold))
    print(f"Saved model artifacts to {outdir}; threshold={threshold:.6f}")
if __name__ == "__main__":
    main()
