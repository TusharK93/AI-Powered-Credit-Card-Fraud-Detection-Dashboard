# MLflow live tracing, metrics and artifacts

Optional observability for the demo scorer. It does **not** make the heuristic demo a validated fraud model.

## What is recorded

| Where | What | When |
|---|---|---|
| **Traces** tab (`fraud-detection-inference`) | One span per scoring call: feature names/count, score, threshold, flag, mode, latency, request id. Failed scorings are traced with status ERROR. | Every request, live |
| **Runs** tab, one run per web worker | Time-series metrics: `prediction_score`, `prediction_threshold`, `score_margin`, `prediction_flagged`, `scoring_latency_ms`, `predictions_total`, `flagged_total`, `flagged_rate`, `scoring_errors_total`, `issue_*_total`. Tags: service, git commit, scorer mode. | Every request, live |
| Run **Artifacts** | `monitoring/summary.json`: totals, flag rate, score and latency percentiles, score histogram. | Every 25 predictions / 5 min, and on shutdown |
| Training experiment (`fraud-detection-training`) | Params, dataset stats, per-epoch loss, validation-error percentiles, threshold, held-out ROC-AUC / precision / recall / F1 / confusion counts, model bundle artifacts. | `train_model.py --mlflow` |

Raw transaction values are never sent to MLflow. MLflow work happens in a background thread: a slow or dead MLflow server cannot slow down or break scoring.

## Why "not connecting on Render" happens (checklist)

1. **mlflow not installed** - the build command must use `requirements-observability.txt`.
2. **Tracking URI is localhost** - on Render `127.0.0.1` is the dashboard container itself. Use the public https URL of a separate MLflow server.
3. **Server asleep / unreachable** - free Render services sleep; the app retries every 30 s.
4. **Wrong or missing credentials** - set `MLFLOW_TRACKING_USERNAME` / `MLFLOW_TRACKING_PASSWORD`.
5. **Artifact upload fails** - the server must run with `--serve-artifacts` and a writable `--artifacts-destination`.

Call `GET https://<your-dashboard>.onrender.com/observability/status/` with header `X-Status-Token: <OBSERVABILITY_STATUS_TOKEN>`. `ready: true` means connected; otherwise `last_error` says exactly why.

## Deploy on Render

1. Create a **Postgres** database in the same region. Copy its *Internal Database URL*.
2. Deploy `render.yaml` (Blueprint). It creates `autoencoder-fraud-dashboard` and `mlflow-tracking-server`.
3. On `mlflow-tracking-server` set `MLFLOW_BACKEND_STORE_URI` (the Postgres URL) and `MLFLOW_ADMIN_PASSWORD` (letters/digits only).
4. On the dashboard service set `MLFLOW_TRACKING_URI=https://<mlflow service>.onrender.com`, `MLFLOW_TRACKING_USERNAME=admin`, `MLFLOW_TRACKING_PASSWORD=<same password>`.
5. Redeploy the dashboard, open `/health/`, then `/observability/status/`, submit a transaction, and open the MLflow UI.

The disk on the MLflow service needs a paid instance type; without a disk, artifacts are lost on redeploy. You can instead point `MLFLOW_ARTIFACTS_DESTINATION` at S3-compatible storage.

## Run locally (Windows PowerShell)

```powershell
python -m pip install -r requirements-observability.txt
python -m mlflow server --host 127.0.0.1 --port 5000 --serve-artifacts      # terminal 1
$env:MLFLOW_TRACING_ENABLED = "true"; $env:MLFLOW_TRACKING_URI = "http://127.0.0.1:5000"
python manage.py runserver                                                  # terminal 2
```

## Log model training

```powershell
python -m pip install -r requirements-ml.txt -r requirements-observability.txt
$env:MLFLOW_TRACKING_URI = "https://<your mlflow>.onrender.com"
$env:MLFLOW_TRACKING_USERNAME = "admin"; $env:MLFLOW_TRACKING_PASSWORD = "<password>"
python train_model.py --data "C:\path\to\card_transdata.csv" --epochs 20 --mlflow
```

Evaluation uses genuine rows and fraud rows that were not used for fitting or for choosing the threshold. Report those metrics only with the data description (class balance, sample caps).

## Configuration reference

| Variable | Default | Purpose |
|---|---|---|
| `MLFLOW_TRACING_ENABLED` | `false` | Turn live tracing on |
| `MLFLOW_TRACKING_URI` | `http://127.0.0.1:5000` | Server root URL (no path) |
| `MLFLOW_TRACKING_USERNAME` / `PASSWORD` | unset | Basic auth |
| `MLFLOW_EXPERIMENT_NAME` | `fraud-detection-inference` | Inference experiment |
| `MLFLOW_TRAINING_EXPERIMENT_NAME` | `fraud-detection-training` | Training experiment |
| `MLFLOW_RECONNECT_SECONDS` | `30` | Retry interval when unreachable |
| `MLFLOW_ARTIFACT_EVERY_N` / `_SECONDS` | `25` / `300` | Summary artifact cadence |
| `MLFLOW_HTTP_REQUEST_TIMEOUT` / `_MAX_RETRIES` | `10` / `2` | Fail-fast client limits |
| `OBSERVABILITY_STATUS_TOKEN` | unset | Enables `/observability/status/` |

Before calling this production grade, still add: rate limiting, drift monitoring, retention controls, alerting, load testing and independent model evaluation.
