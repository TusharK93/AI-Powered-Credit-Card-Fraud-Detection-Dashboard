# Signal — Autoencoder Transaction Anomaly Dashboard

A Django portfolio web app based on `autoencoders-for-anomalies-reconstruct-detect.ipynb`. It provides a responsive UI, transaction-feature form, reconstruction-error score, threshold comparison, recent prediction history, health endpoint, and Render deployment configuration.

## Important model note

The uploaded notebook expects Kaggle's `card_transdata.csv`, which was not included with the notebook. Therefore the site starts in **synthetic demo mode** and trains a small autoencoder on generated sample data at first use. This proves the UI flow only; it is **not trained on real card transactions** and must not be used for real fraud decisions.

To use a model trained on your dataset, create the artifact bundle described below. When the three files exist, the app loads that trained model automatically.

## Run locally (Windows)

```powershell
py -3.11 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open http://127.0.0.1:8000. Health check: http://127.0.0.1:8000/health/

TensorFlow can be large to install. If its installation fails on your machine, check the Python version and TensorFlow's supported Windows/Python combinations.

## Train on the real dataset

1. Obtain the dataset you are authorized to use; keep it out of Git if its license or privacy terms require that.
2. Ensure the CSV contains these columns: `distance_from_home`, `distance_from_last_transaction`, `ratio_to_median_purchase_price`, `repeat_retailer`, `used_chip`, `used_pin_number`, `online_order`, and `fraud`.
3. Install dependencies, then run:

```powershell
python train_model.py --data path\to\card_transdata.csv --epochs 20
```

This creates `model_artifacts/autoencoder.keras`, `model_artifacts/scaler.npz`, and `model_artifacts/threshold.txt`. Keep all three together. To deploy the real model on Render, include the artifacts in the repository only if the dataset/model license and artifact size permit it, or use an appropriate model-storage solution. Do not commit private transaction data.

## Deploy on Render

1. Create a GitHub repository and upload this project's files.
2. In Render, choose **New + → Blueprint** and select the repository; Render reads `render.yaml`.
3. Confirm the build and start commands. The app uses SQLite by default, which may not persist across Render redeploys/restarts on many service setups. For persistent prediction history, add a Render PostgreSQL database and set `DATABASE_URL` to its internal connection string.
4. Set `DEBUG=false` and a strong `SECRET_KEY` in environment variables. Set `ALLOWED_HOSTS` if needed.
5. Open `/health/` to verify the service is responding.

For persistent production deployments, add Django migrations to the release/start process and configure a managed database. The current Procfile is intentionally minimal for a straightforward first deployment.

## Resume bullet (edit to match what you actually built)

**Autoencoder-Based Transaction Anomaly Detection Dashboard | Python, TensorFlow/Keras, Django, scikit-learn, PostgreSQL/Render**
- Built a Django dashboard that scores transaction feature vectors using autoencoder reconstruction error and a configurable anomaly threshold.
- Added a responsive UI, prediction-history logging, health endpoint, and cloud deployment configuration.
- Trained on genuine transactions and evaluated threshold/recall **only after replacing demo artifacts with the real dataset and recording measured results**.

Do not claim a specific accuracy, recall, or production impact unless you have measured it on a held-out dataset.
