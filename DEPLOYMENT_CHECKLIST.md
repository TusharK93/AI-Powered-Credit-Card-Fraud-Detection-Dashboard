# Deployment checklist

- [ ] Set a strong `SECRET_KEY` in Render; never commit it.
- [ ] Keep `DEBUG=false` and restrict `ALLOWED_HOSTS` to the deployed hostname(s).
- [ ] Confirm `/health/` returns HTTP 200.
- [ ] Confirm `/ready/` returns HTTP 200 and database status `ok`.
- [ ] Run `python manage.py check` and `python manage.py test` before pushing.
- [ ] Confirm Render logs contain request IDs and no raw transaction feature values.
- [ ] Use managed PostgreSQL if prediction history must survive restarts/redeploys.
- [ ] Only enable the autoencoder after supplying all artifacts and the optional ML dependencies.
- [ ] Document validation data, threshold-selection method, and measured held-out metrics before describing this as a fraud detector.

## MLflow live tracing

- [ ] Render build command installs `requirements-observability.txt` (not only `requirements.txt`).
- [ ] The MLflow server is running and reachable at a public `https://` URL (not `127.0.0.1`).
- [ ] The MLflow server uses Postgres + `--serve-artifacts` + a writable artifacts location.
- [ ] `MLFLOW_TRACING_ENABLED=true`, `MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, `MLFLOW_TRACKING_PASSWORD` are set on the dashboard service.
- [ ] `GET /observability/status/` (header `X-Status-Token`) shows `"ready": true` and `"last_error": null`.
- [ ] After one test transaction, the MLflow UI shows a trace, run metrics and `monitoring/summary.json`.
- [ ] Verify no raw transaction inputs or secrets appear in traces, metrics or logs.
- [ ] Validate model quality on held-out data before making performance claims.
