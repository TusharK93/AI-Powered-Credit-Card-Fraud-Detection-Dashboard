<<<<<<< HEAD
# Signal — Transaction Anomaly Dashboard

A Django portfolio project demonstrating a small, observable web service for transaction-feature scoring. It includes validated input, configurable scoring threshold, request IDs, structured application logs, health/readiness endpoints, prediction-history persistence, database migrations, automated tests, and Render deployment configuration.

> **Model honesty:** the default deployed scorer is a hand-written heuristic for demonstrating application plumbing. It is not a trained fraud detector, has no validated fraud metrics, and must not be used to approve/decline transactions or make real financial decisions. A trained autoencoder can be loaded only when a complete artifact bundle and the optional TensorFlow dependency are configured.

## Architecture

```text
Browser form
    ↓
Django form validation
    ↓
Scoring service ── trained artifact bundle present? ── yes → optional Keras autoencoder
    │                                                   no  → transparent heuristic demo
    ↓
Threshold comparison
    ↓
PredictionLog (score, threshold, mode, flag; no raw feature payload)
    ↓
Dashboard history + application logs
```

## Features

- Environment-driven settings and production secret-key validation.
- Request correlation IDs returned as `X-Request-ID`.
- Request duration/status logging; submitted feature values are not logged.
- Liveness probe at `/health/` and database readiness probe at `/ready/`.
- Server-side validation for numeric, finite, non-negative and binary fields.
- Configurable heuristic threshold through `DEMO_ANOMALY_THRESHOLD` (0 to 1).
- Prediction history indexes and a migration that renames the stored metric to the generic `score` field.
- Django regression tests for scoring, validation, endpoints, and history creation.
- Lightweight runtime requirements; TensorFlow is optional rather than imported for every demo request.

## Run locally on Windows

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
```

Open `http://127.0.0.1:8000/`. Health checks: `/health/` and `/ready/`.

## Configuration

Copy `.env.example` as a reference. Django does not automatically load `.env`; set environment variables in PowerShell or your hosting dashboard. Example PowerShell session:

```powershell
$env:DEBUG = "True"
$env:DEMO_ANOMALY_THRESHOLD = "0.50"
$env:LOG_LEVEL = "INFO"
```

For production, set a strong random `SECRET_KEY`, `DEBUG=False`, and an appropriate `ALLOWED_HOSTS`. Never commit `.env`, credentials, or private transaction data.

## Optional trained autoencoder

The repository does not include the original transaction dataset or trained model artifacts. To train locally, install the optional ML dependencies:

```powershell
pip install -r requirements-ml.txt
python train_model.py --data path	o\card_transdata.csv --epochs 20
```

The CSV must contain the seven feature columns in `detector/services.py` and a `fraud` target column. The training script fits on rows marked `fraud == 0` and writes `autoencoder.keras`, `scaler.npz`, and `threshold.txt` to `model_artifacts/`. Validate the model on an appropriate held-out set before making any performance claims. To serve this model, include `requirements-ml.txt` dependencies in the runtime and supply all three artifacts via `MODEL_ARTIFACTS_DIR` or the default `model_artifacts/` directory. TensorFlow inference can require more memory than the heuristic demo.

## MLflow experiment tracking and tracing\n\nSee [`MLFLOW_SETUP.md`](MLFLOW_SETUP.md) for installation, configuration, safe inference tracing, and opt-in training experiment logging. Install `requirements-observability.txt` only when you want MLflow integration; tracing is disabled by default.\n\n## Deploy to Render

1. Push this repository to GitHub and create a Render Blueprint from `render.yaml`.
2. Render installs the lightweight runtime dependencies and runs migrations before Gunicorn starts.
3. Confirm `SECRET_KEY` is generated and `DEBUG=false` in the service environment.
4. Visit `/health/` for liveness and `/ready/` for database readiness.
5. For durable prediction history, configure a managed PostgreSQL database and set `DATABASE_URL`. Local SQLite files may not persist across instance replacement/redeploys.

The free-tier environment and SQLite are suitable for a portfolio demo, not a high-availability financial service. Before production use, add authentication/authorization, rate limiting, persistent managed storage, monitoring/alerting, data-retention policy, threat modelling, and independent model validation.

## Resume wording (accurate for current implementation)

**Transaction Anomaly Dashboard | Python, Django, NumPy, PostgreSQL-ready, Render**
- Built a Django dashboard with validated transaction-feature inputs, configurable anomaly threshold, and minimal prediction history.
- Added request correlation IDs, duration/status logging, liveness/readiness endpoints, environment-based security settings, and regression tests.
- Designed optional lazy loading for a trained Keras autoencoder artifact bundle; deployed fallback is explicitly labelled as a heuristic demo until trained artifacts and evaluation evidence are supplied.

Do not claim fraud detection accuracy, production impact, or Mastercard affiliation without evidence. This is an independent portfolio project.
=======
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
>>>>>>> f339c19469c5a76f6e33e0968448b505cfb384cc
