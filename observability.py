"""Non-blocking MLflow observability for transaction scoring.
 
What gets recorded when MLFLOW_TRACING_ENABLED=true
---------------------------------------------------
* **Traces** (live, per request): one span per scoring call with safe metadata only
  (feature names/count, score, threshold, flag, mode, latency, request id). Raw feature
  values are never sent to MLflow.
* **Metrics** (live, time series): one long-lived MLflow run per web worker. Every
  prediction logs prediction_score, prediction_threshold, prediction_flagged,
  score_margin, scoring_latency_ms and running totals; errors are counted too.
* **Artifacts**: a monitoring summary (JSON: totals, flag rate, score/latency
  percentiles, score histogram) is re-uploaded every N predictions / M seconds and once
  more on shutdown.
 
Design rules
------------
* A request thread never waits for MLflow. The only work done on the request path is
  opening/closing a span; metrics, params, artifacts and (re)connection run in one
  background daemon thread fed by a bounded queue.
* MLflow being down, slow, missing or misconfigured must never break scoring. Every
  failure is logged with logger.exception (first time) / logger.warning (repeats) and
  the worker retries the connection every MLFLOW_RECONNECT_SECONDS.
* get_status() reports exactly why the connection is not working.
"""
from __future__ import annotations
 
import atexit
import logging
import math
import os
import platform
import queue
import threading
import time
from collections import deque
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
 
logger = logging.getLogger("detector.observability")
 
TRUTHY = {"1", "true", "yes", "on"}
DEFAULT_URI = "http://127.0.0.1:5000"
DEFAULT_EXPERIMENT = "fraud-detection-inference"
LOCAL_HOSTS = {"127.0.0.1", "localhost", "0.0.0.0", "::1"}
SPAN_NAME = "detector.score_transaction"
POLL_SECONDS = 0.5
 
 
# --------------------------------------------------------------------------- helpers
def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("invalid_env_int name=%s value=%r using_default=%s", name, raw, default)
        return default
 
 
def tracing_enabled() -> bool:
    return os.environ.get("MLFLOW_TRACING_ENABLED", "false").strip().lower() in TRUTHY
 
 
def tracking_uri() -> str:
    return os.environ.get("MLFLOW_TRACKING_URI", "").strip() or DEFAULT_URI
 
 
def redact_uri(uri: str) -> str:
    """Return scheme://host:port/path without any user:password part or query string."""
    try:
        parts = urlsplit(uri)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        return urlunsplit((parts.scheme, host, parts.path, "", ""))
    except ValueError:
        return "<invalid MLFLOW_TRACKING_URI>"
 
 
def _scrub(text: str) -> str:
    for name in ("MLFLOW_TRACKING_PASSWORD", "MLFLOW_TRACKING_TOKEN"):
        secret = os.environ.get(name, "")
        if secret:
            text = text.replace(secret, "***")
    return text
 
 
def _basic_auth():
    user = os.environ.get("MLFLOW_TRACKING_USERNAME", "")
    password = os.environ.get("MLFLOW_TRACKING_PASSWORD", "")
    return (user, password) if user and password else None
 
 
def apply_client_timeouts() -> None:
    """Fail fast instead of letting MLflow retry for minutes (set before using MLflow)."""
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_TIMEOUT", "10")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_MAX_RETRIES", "2")
    os.environ.setdefault("MLFLOW_HTTP_REQUEST_BACKOFF_FACTOR", "1")
    os.environ.setdefault("MLFLOW_ENABLE_ASYNC_TRACE_LOGGING", "true")
 
 
def probe_tracking_server(uri: str, timeout=(3.0, 8.0)) -> None:
    """Raise RuntimeError with a human-readable reason if an http(s) MLflow server is unusable."""
    if not uri.lower().startswith(("http://", "https://")):
        return  # file:, sqlite:, databricks: ... cannot be probed over HTTP
    import requests
 
    safe = redact_uri(uri)
    try:
        response = requests.get(uri.rstrip("/") + "/health", timeout=timeout, auth=_basic_auth())
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(
            f"cannot reach MLflow server at {safe} ({type(exc).__name__}). Check the URL, that the "
            "server is running (free Render services sleep), and that it is publicly reachable."
        ) from exc
    if response.status_code in (401, 403):
        raise RuntimeError(
            f"MLflow server at {safe} rejected the credentials (HTTP {response.status_code}). "
            "Check MLFLOW_TRACKING_USERNAME / MLFLOW_TRACKING_PASSWORD."
        )
    if response.status_code == 404:
        return  # hosted servers (e.g. DagsHub) have no /health route; real calls will report any problem
    if response.status_code >= 400:
        raise RuntimeError(
            f"MLflow server at {safe} answered HTTP {response.status_code} for /health. "
            "Check MLFLOW_TRACKING_URI (it must be the server root, without a path)."
        )
 
 
def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
 
 
def _percentile(sorted_values, pct):
    if not sorted_values:
        return None
    index = min(len(sorted_values) - 1, max(0, int(round(pct / 100 * (len(sorted_values) - 1)))))
    return sorted_values[index]
 
 
def _run_tags() -> dict:
    return {
        "purpose": "inference-monitoring",
        "service": os.environ.get("RENDER_SERVICE_NAME", "local"),
        "instance": os.environ.get("RENDER_INSTANCE_ID", platform.node()),
        "git_commit": os.environ.get("RENDER_GIT_COMMIT", "unknown")[:40],
        "pid": str(os.getpid()),
        "python": platform.python_version(),
    }
 
 
# --------------------------------------------------------------------------- reporter
class _Reporter:
    """Background worker that owns the MLflow client, the monitoring run and all uploads."""
 
    def __init__(self, max_queue: int = 2000):
        self._lock = threading.Lock()
        self._max_queue = max_queue
        self._thread = None
        self._pid = None
        self._init_state()
 
    def _init_state(self):
        self._queue = queue.Queue(maxsize=self._max_queue)
        self._stop = threading.Event()
        self.ready = threading.Event()
        self._client = None
        self._types = None  # (Metric, Param)
        self.run_id = None
        self.experiment_id = None
        self.last_error = None
        self.last_error_at = None
        self.last_artifact_at = None
        self.last_artifact_error = None
        self.dropped = 0
        self.processed = 0
        self._connect_failures = 0
        self._batch_failures = 0
        self._step = 0
        self._total = 0
        self._flagged = 0
        self._errors = 0
        self._issues = {}
        self._scores = deque(maxlen=2000)
        self._latencies = deque(maxlen=2000)
        self._since_artifact = 0
        self._last_artifact_mono = time.monotonic()
        self._mode = None
        self._feature_params_logged = False
 
    # ---- lifecycle -------------------------------------------------------------
    def ensure_started(self):
        pid = os.getpid()
        with self._lock:
            if self._thread is not None and self._thread.is_alive() and self._pid == pid:
                return
            if self._pid is not None and self._pid != pid:
                self._init_state()  # forked gunicorn worker: never reuse the parent's state
            self._stop.clear()
            self._pid = pid
            self._thread = threading.Thread(target=self._run, name="mlflow-reporter", daemon=True)
            self._thread.start()
 
    def shutdown(self, timeout: float = 8.0):
        thread = self._thread
        if thread is None or not thread.is_alive() or self._pid != os.getpid():
            return
        self._stop.set()
        thread.join(timeout)
 
    def submit(self, event: dict):
        """Queue an event for the worker. Never blocks and never raises."""
        try:
            self.ensure_started()
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped += 1
        except Exception:
            logger.exception("mlflow_event_submit_failed")
 
    # ---- worker loop -----------------------------------------------------------
    def _run(self):
        reconnect_seconds = max(5, _env_int("MLFLOW_RECONNECT_SECONDS", 30))
        try:
            while not self._stop.is_set():
                if not self.ready.is_set():
                    if not self._connect():
                        self._discard_pending()
                        self._stop.wait(reconnect_seconds)
                        continue
                batch = self._collect_batch()
                if batch:
                    self._handle(batch)
                self._maybe_artifact()
            self._final_flush()
        except Exception:
            logger.exception("mlflow_reporter_crashed")
            self.ready.clear()
 
    def _collect_batch(self):
        batch = []
        try:
            batch.append(self._queue.get(timeout=POLL_SECONDS))
        except queue.Empty:
            return batch
        while len(batch) < 200:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch
 
    def _discard_pending(self):
        discarded = 0
        while True:
            try:
                self._queue.get_nowait()
                discarded += 1
            except queue.Empty:
                break
        self.dropped += discarded
 
    # ---- connection ------------------------------------------------------------
    def _connect(self) -> bool:
        uri = tracking_uri()
        safe = redact_uri(uri)
        try:
            apply_client_timeouts()
            host = (urlsplit(uri).hostname or "").lower()
            if os.environ.get("RENDER", "").lower() == "true" and host in LOCAL_HOSTS:
                raise RuntimeError(
                    f"MLFLOW_TRACKING_URI points to {safe}, which is this Render container itself. "
                    "Set it to the public https URL of your MLflow server."
                )
            probe_tracking_server(uri)
            import mlflow
            from mlflow.entities import Metric, Param
            from mlflow.tracking import MlflowClient
 
            mlflow.set_tracking_uri(uri)
            experiment_name = os.environ.get("MLFLOW_EXPERIMENT_NAME", DEFAULT_EXPERIMENT)
            experiment = mlflow.set_experiment(experiment_name)
            client = MlflowClient(tracking_uri=uri)
            if self.run_id is None:
                stamp = time.strftime("%Y%m%d-%H%M%S")
                tags = _run_tags()
                run = client.create_run(
                    experiment.experiment_id,
                    tags=tags,
                    run_name=f"inference-{tags['service']}-{stamp}-pid{os.getpid()}",
                )
                run_id = run.info.run_id
                client.log_batch(run_id, params=[
                    Param("demo_anomaly_threshold", os.environ.get("DEMO_ANOMALY_THRESHOLD", "0.50")),
                    Param("model_artifacts_dir", os.environ.get("MODEL_ARTIFACTS_DIR", "default")),
                    Param("log_level", os.environ.get("LOG_LEVEL", "INFO")),
                ])
                self.run_id = run_id
            self._client = client
            self._types = (Metric, Param)
            self.experiment_id = experiment.experiment_id
            self._connect_failures = 0
            self._batch_failures = 0
            self.last_error = None
            self.ready.set()
            logger.info("mlflow_tracing_initialized uri=%s experiment=%s run_id=%s",
                        safe, experiment_name, self.run_id)
            return True
        except ImportError as exc:
            self._record_connect_failure(
                safe, "the 'mlflow' package is not installed in this environment. Build with "
                      "'pip install -r requirements-observability.txt'.", exc)
        except Exception as exc:
            self._record_connect_failure(safe, str(exc) or type(exc).__name__, exc)
        return False
 
    def _record_connect_failure(self, safe_uri, message, exc):
        self._connect_failures += 1
        self.last_error = _scrub(f"{message} [{type(exc).__name__}]")[:500]
        self.last_error_at = datetime.now(timezone.utc).isoformat()
        if self._connect_failures == 1:
            logger.exception("mlflow_connect_failed uri=%s reason=%s", safe_uri, self.last_error)
        else:
            logger.warning("mlflow_connect_failed uri=%s attempt=%s reason=%s",
                           safe_uri, self._connect_failures, self.last_error)
 
    # ---- event handling --------------------------------------------------------
    def _metric(self, key, value, ts, step):
        number = _finite(value)
        return None if number is None else self._types[0](key, number, ts, step)
 
    def _handle(self, batch):
        metrics = []
        now_ms = int(time.time() * 1000)
        for event in batch:
            kind = event.get("kind")
            ts = int(event.get("ts", now_ms))
            self._step += 1
            step = self._step
            if kind == "prediction":
                self._total += 1
                self._flagged += int(bool(event.get("flagged")))
                self._since_artifact += 1
                score, latency = _finite(event.get("score")), _finite(event.get("latency_ms"))
                if score is not None:
                    self._scores.append(score)
                if latency is not None:
                    self._latencies.append(latency)
                threshold = _finite(event.get("threshold"))
                margin = None if score is None or threshold is None else score - threshold
                for key, value in (
                    ("prediction_score", score),
                    ("prediction_threshold", threshold),
                    ("score_margin", margin),
                    ("prediction_flagged", 1.0 if event.get("flagged") else 0.0),
                    ("scoring_latency_ms", latency),
                    ("predictions_total", self._total),
                    ("flagged_total", self._flagged),
                    ("flagged_rate", self._flagged / self._total),
                ):
                    metric = self._metric(key, value, ts, step)
                    if metric is not None:
                        metrics.append(metric)
                self._sync_mode_and_features(event)
            elif kind == "error":
                self._errors += 1
                metrics.extend(m for m in (
                    self._metric("scoring_errors_total", self._errors, ts, step),
                    self._metric("scoring_error_latency_ms", event.get("latency_ms"), ts, step),
                ) if m is not None)
            elif kind == "issue":
                name = str(event.get("name", "unknown"))[:60]
                self._issues[name] = self._issues.get(name, 0) + 1
                metric = self._metric(f"issue_{name}_total", self._issues[name], ts, step)
                if metric is not None:
                    metrics.append(metric)
        try:
            for start in range(0, len(metrics), 1000):
                self._client.log_batch(self.run_id, metrics=metrics[start:start + 1000])
            self.processed += len(batch)
            self._batch_failures = 0
        except Exception:
            self._batch_failures += 1
            self.dropped += len(batch)
            logger.exception("mlflow_log_batch_failed run_id=%s events=%s consecutive_failures=%s",
                             self.run_id, len(batch), self._batch_failures)
            self.last_error = f"log_batch failed ({self._batch_failures} in a row); see application logs"
            self.last_error_at = datetime.now(timezone.utc).isoformat()
            if self._batch_failures >= 3:
                self.ready.clear()  # force a full reconnect (probe + set_experiment)
 
    def _sync_mode_and_features(self, event):
        try:
            mode = event.get("mode")
            if mode and mode != self._mode:
                self._client.set_tag(self.run_id, "scorer_mode", str(mode))
                self._mode = mode
            names = event.get("feature_names")
            if names and not self._feature_params_logged:
                self._client.log_batch(self.run_id, params=[
                    self._types[1]("feature_count", str(len(names))),
                    self._types[1]("feature_names", ",".join(names)[:5000]),
                ])
                self._feature_params_logged = True
        except Exception:
            self._feature_params_logged = True  # params are immutable; do not retry forever
            logger.exception("mlflow_tag_or_param_failed run_id=%s", self.run_id)
 
    # ---- artifacts -------------------------------------------------------------
    def _summary(self) -> dict:
        import numpy as np
 
        scores = sorted(self._scores)
        latencies = sorted(self._latencies)
        histogram = None
        if scores:
            counts, edges = np.histogram(np.asarray(scores, dtype=float), bins=10)
            histogram = {"bin_edges": [round(float(e), 6) for e in edges],
                         "counts": [int(c) for c in counts]}
        mean = lambda values: (sum(values) / len(values)) if values else None  # noqa: E731
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "run_id": self.run_id,
            "scorer_mode": self._mode,
            "predictions_total": self._total,
            "flagged_total": self._flagged,
            "flagged_rate": (self._flagged / self._total) if self._total else None,
            "scoring_errors_total": self._errors,
            "issues": dict(self._issues),
            "dropped_events": self.dropped,
            "window_size": len(scores),
            "score": {"mean": mean(scores), "p50": _percentile(scores, 50),
                      "p95": _percentile(scores, 95), "max": scores[-1] if scores else None},
            "latency_ms": {"mean": mean(latencies), "p50": _percentile(latencies, 50),
                           "p95": _percentile(latencies, 95), "p99": _percentile(latencies, 99),
                           "max": latencies[-1] if latencies else None},
            "score_histogram": histogram,
            "privacy_note": "Aggregates only; no raw transaction feature values are stored.",
        }
 
    def _maybe_artifact(self, force: bool = False):
        if not self.ready.is_set() or self._since_artifact == 0:
            return
        every_n = max(1, _env_int("MLFLOW_ARTIFACT_EVERY_N", 25))
        every_s = max(10, _env_int("MLFLOW_ARTIFACT_EVERY_SECONDS", 300))
        due = (force or self._since_artifact >= every_n
               or time.monotonic() - self._last_artifact_mono >= every_s)
        if not due:
            return
        self._last_artifact_mono = time.monotonic()  # back off even if the upload fails
        try:
            self._client.log_dict(self.run_id, self._summary(), "monitoring/summary.json")
            self._since_artifact = 0
            self.last_artifact_at = datetime.now(timezone.utc).isoformat()
            self.last_artifact_error = None
        except Exception as exc:
            self.last_artifact_error = _scrub(f"{type(exc).__name__}: {exc}")[:300]
            logger.exception(
                "mlflow_artifact_upload_failed run_id=%s hint='start the MLflow server with "
                "--serve-artifacts and a writable --artifacts-destination'", self.run_id)
 
    def _final_flush(self):
        if not self.ready.is_set():
            self._discard_pending()
            return
        batch = []
        while True:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        if batch:
            self._handle(batch)
        self._maybe_artifact(force=True)
        try:
            self._client.set_terminated(self.run_id, "FINISHED")
            self.run_id = None  # a later restart creates a fresh run
        except Exception:
            logger.exception("mlflow_run_terminate_failed run_id=%s", self.run_id)
        self.ready.clear()
 
    # ---- introspection ---------------------------------------------------------
    def status(self) -> dict:
        return {
            "enabled": tracing_enabled(),
            "ready": self.ready.is_set(),
            "tracking_uri": redact_uri(tracking_uri()),
            "experiment": os.environ.get("MLFLOW_EXPERIMENT_NAME", DEFAULT_EXPERIMENT),
            "experiment_id": self.experiment_id,
            "run_id": self.run_id,
            "worker_alive": bool(self._thread and self._thread.is_alive()),
            "queued_events": self._queue.qsize(),
            "processed_events": self.processed,
            "dropped_events": self.dropped,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "last_artifact_at": self.last_artifact_at,
            "last_artifact_error": self.last_artifact_error,
            "pid": os.getpid(),
        }
 
 
_reporter = _Reporter()
atexit.register(lambda: _reporter.shutdown())
 
 
# --------------------------------------------------------------------------- spans
def _open_span(values, request_id):
    """Open an MLflow span; return (context_manager, span) or (None, None) on any failure."""
    try:
        import mlflow
 
        cm = mlflow.start_span(name=SPAN_NAME, span_type="CHAIN")
        span = cm.__enter__()
    except Exception:
        logger.exception("mlflow_span_open_failed")
        return None, None
    try:
        span.set_inputs({
            "feature_count": len(values),
            "feature_names": sorted(str(key) for key in values.keys()),
        })
        if request_id:
            span.set_attributes({"request_id": str(request_id)})
            if hasattr(mlflow, "update_current_trace"):
                mlflow.update_current_trace(tags={"request_id": str(request_id)})
    except Exception:
        logger.exception("mlflow_span_annotate_failed")
    return cm, span
 
 
def _close_span(cm, span, result=None, latency_ms=None, exc=None):
    if cm is None:
        return
    try:
        if exc is None and span is not None and result is not None:
            span.set_outputs({
                "score": float(result["score"]),
                "threshold": float(result["threshold"]),
                "flagged": bool(result["flagged"]),
                "mode": str(result["mode"]),
            })
            span.set_attributes({"latency_ms": round(float(latency_ms), 3)})
    except Exception:
        logger.exception("mlflow_span_outputs_failed")
    try:
        if exc is None:
            cm.__exit__(None, None, None)
        else:
            cm.__exit__(type(exc), exc, exc.__traceback__)
    except BaseException as inner:  # MLflow re-raises the traced exception; that is expected
        if inner is not exc:
            logger.exception("mlflow_span_close_failed")
 
 
# --------------------------------------------------------------------------- public API
def trace_scoring(values, scorer, request_id=None):
    """Run ``scorer(values)`` exactly once and record it in MLflow without ever affecting it."""
    if not tracing_enabled():
        return scorer(values)
 
    reporter = _reporter
    try:
        reporter.ensure_started()
    except Exception:
        logger.exception("mlflow_worker_start_failed")
    cm, span = _open_span(values, request_id) if reporter.ready.is_set() else (None, None)
 
    started = time.perf_counter()
    try:
        result = scorer(values)
    except Exception as exc:
        latency_ms = (time.perf_counter() - started) * 1000
        _close_span(cm, span, exc=exc)
        reporter.submit({"kind": "error", "ts": int(time.time() * 1000),
                         "latency_ms": latency_ms, "error_type": type(exc).__name__})
        logger.warning("scoring_failed_recorded error_type=%s request_id=%s",
                       type(exc).__name__, request_id or "unknown")
        raise
 
    latency_ms = (time.perf_counter() - started) * 1000
    _close_span(cm, span, result=result, latency_ms=latency_ms)
    try:
        reporter.submit({
            "kind": "prediction",
            "ts": int(time.time() * 1000),
            "score": result["score"],
            "threshold": result["threshold"],
            "flagged": result["flagged"],
            "mode": result["mode"],
            "latency_ms": latency_ms,
            "feature_names": sorted(str(key) for key in values.keys()),
        })
    except Exception:
        logger.exception("mlflow_prediction_event_failed")
    return result
 
 
def record_issue(name: str) -> None:
    """Count an operational problem (e.g. a database write failure) as an MLflow metric."""
    if tracing_enabled():
        _reporter.submit({"kind": "issue", "ts": int(time.time() * 1000), "name": name})
 
 
def warm_up() -> None:
    """Start the background connection early (called from /health/ so it connects after deploy)."""
    if tracing_enabled():
        try:
            _reporter.ensure_started()
        except Exception:
            logger.exception("mlflow_warm_up_failed")
 
 
def get_status() -> dict:
    warm_up()
    return _reporter.status()