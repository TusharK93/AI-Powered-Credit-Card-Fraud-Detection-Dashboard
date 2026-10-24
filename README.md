Signal --- Transaction Anomaly Dashboard
A Django portfolio project demonstrating a small, observable web service
for transaction-feature scoring. It includes validated input,
configurable scoring thresholds, request IDs, structured application
logs, health/readiness endpoints, prediction-history persistence,
database migrations, automated tests, and Render deployment
configuration.
Model honesty: The default scorer may be a heuristic demo unless a
complete trained model artifact bundle and the optional ML
dependencies are configured. Do not claim validated fraud-detection
performance or use this portfolio project to approve/decline real
transactions without independent model validation.

Architecture
Browser form
    ↓
Django form validation
    ↓
Scoring service ── complete trained artifact bundle available?
    │                    ├─ yes → optional Keras autoencoder
    │                    └─ no  → demo scoring mode
    ↓
Threshold comparison
    ↓
PredictionLog (score, threshold, mode, flag; no raw feature payload)
    ↓
Dashboard history + application logs
Features
- Environment-driven settings and production secret-key validation.
- Request correlation IDs returned as X-Request-ID.
- Request duration/status logging without logging submitted feature
  values.
- Liveness endpoint at /health/ and database readiness endpoint at
  /ready/.
- Server-side validation for numeric, finite, non-negative, and binary
  fields.
- Configurable demo threshold through DEMO_ANOMALY_THRESHOLD (0 to
  1).
- Prediction-history persistence and database migrations.
- Django regression tests for scoring, validation, endpoints, and
  history creation.
- Lightweight runtime requirements; TensorFlow is optional.
Run locally on Windows
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py test
python manage.py runserver
Open http://127.0.0.1:8000/. Health endpoints: /health/ and
/ready/.
Configuration
Use .env.example as a reference. Django does not automatically load
.env unless the project explicitly configures a dotenv loader; set
environment variables in PowerShell or your hosting dashboard.

Example PowerShell session:
$env:DEBUG = "True"
$env:DEMO_ANOMALY_THRESHOLD = "0.50"
$env:LOG_LEVEL = "INFO"
For production, set a strong random SECRET_KEY, set DEBUG=False, and
configure an appropriate ALLOWED_HOSTS. Never commit .env,
credentials, or private transaction data.
Optional trained autoencoder
The original dataset and trained model artifacts are not included by
default. To train a model, install the optional machine-learning
dependencies:
pip install -r requirements-ml.txt
python train_model.py --data path\to\card_transdata.csv --epochs 20
The CSV is expected to contain these feature columns:
- distance_from_home
- distance_from_last_transaction
- ratio_to_median_purchase_price
- repeat_retailer
- used_chip
- used_pin_number
- online_order
- fraud (target column)
The training script is described as fitting on rows where fraud == 0
and producing autoencoder.keras, scaler.npz, and threshold.txt
under model_artifacts/. Keep the artifacts together. To serve a
trained model, install the optional runtime dependencies and configure
MODEL_ARTIFACTS_DIR if the artifacts are not in the default
model_artifacts/ directory.

Validate the model on an appropriate held-out dataset before making any
performance claims. TensorFlow inference may require more memory than
the demo scorer.
MLflow experiment tracking and tracing
See [`MLFLOW_SETUP.md`](MLFLOW_SETUP.md) for installation,
configuration, safe inference tracing, and optional training experiment
logging. Install requirements-observability.txt only when MLflow
integration is needed; tracing is disabled by default.
Deploy to Render
1. Push this repository to GitHub and create a Render Blueprint from
   render.yaml.
2. Confirm that the build/start commands install dependencies and run
   migrations before Gunicorn starts.
3. Set a generated SECRET_KEY and DEBUG=false in the service
   environment.
4. Visit /health/ for liveness and /ready/ for database readiness.
5. For durable prediction history, configure a managed PostgreSQL
   database and set DATABASE_URL. Local SQLite data may not persist
   across instance replacement or redeployments.
The free-tier environment and SQLite are suitable for a portfolio demo,
not a high-availability financial service. Before production use, add
authentication/authorization, rate limiting, persistent managed storage,
monitoring/alerting, a data-retention policy, threat modelling, and
independent model validation.
Resume wording (accurate for the current implementation)
Transaction Anomaly Dashboard | Python, Django, NumPy,
PostgreSQL-ready, Render
- Built a Django dashboard with validated transaction-feature inputs,
  a configurable anomaly threshold, and prediction history.
- Added request correlation IDs, duration/status logging,
  health/readiness endpoints, environment-based security settings, and
  regression tests.
- Designed optional loading for a trained Keras autoencoder artifact
  bundle; describe the deployed scoring mode accurately and do not
  claim model accuracy without evaluation evidence.
Do not claim a specific accuracy, recall, production impact, or
Card affiliation without evidence. This is an independent
portfolio project.