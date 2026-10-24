"""Tests for the MLflow observability layer using a fake in-memory ``mlflow`` package.

No MLflow server or network is needed. Run with:  python manage.py test detector.test_observability
"""
import contextlib
import os
import sys
import time
import types
import unittest
from unittest import mock

from detector import observability


def wait_for(condition, timeout=8.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def build_fake_mlflow(record):
    """Create fake mlflow, mlflow.entities and mlflow.tracking modules recording every call."""
    mlflow = types.ModuleType("mlflow")
    entities = types.ModuleType("mlflow.entities")
    tracking = types.ModuleType("mlflow.tracking")

    class Metric:
        def __init__(self, key, value, timestamp, step):
            self.key, self.value, self.timestamp, self.step = key, value, timestamp, step

    class Param:
        def __init__(self, key, value):
            self.key, self.value = key, value

    class Span:
        def set_inputs(self, data): record["span_inputs"].append(data)
        def set_outputs(self, data): record["span_outputs"].append(data)
        def set_attributes(self, data): record["span_attrs"].append(data)

    @contextlib.contextmanager
    def start_span(name=None, span_type=None):
        record["spans"].append(name)
        try:
            yield Span()
        except Exception as exc:
            record["span_errors"].append(type(exc).__name__)
            raise

    class Client:
        def __init__(self, tracking_uri=None): pass
        def create_run(self, experiment_id, start_time=None, tags=None, run_name=None):
            record["runs"].append({"experiment_id": experiment_id, "tags": tags, "name": run_name})
            return types.SimpleNamespace(info=types.SimpleNamespace(run_id="run-1"))
        def log_batch(self, run_id, metrics=(), params=(), tags=()):
            record["metrics"].extend(metrics)
            record["params"].extend(params)
        def set_tag(self, run_id, key, value): record["tags"][key] = value
        def log_dict(self, run_id, dictionary, artifact_file):
            record["artifacts"].append((artifact_file, dictionary))
        def set_terminated(self, run_id, status=None): record["terminated"].append(status)

    mlflow.set_tracking_uri = lambda uri: record.__setitem__("uri", uri)
    mlflow.set_experiment = lambda name: types.SimpleNamespace(experiment_id="exp-1", name=name)
    mlflow.start_span = start_span
    entities.Metric, entities.Param = Metric, Param
    tracking.MlflowClient = Client
    mlflow.entities, mlflow.tracking = entities, tracking
    return {"mlflow": mlflow, "mlflow.entities": entities, "mlflow.tracking": tracking}


def new_record():
    return {"spans": [], "span_inputs": [], "span_outputs": [], "span_attrs": [], "span_errors": [],
            "runs": [], "metrics": [], "params": [], "tags": {}, "artifacts": [], "terminated": []}


def good_scorer(values):
    return {"score": 0.7, "threshold": 0.5, "flagged": True, "mode": "heuristic_demo"}


def failing_scorer(values):
    raise ValueError("bad input")


VALUES = {"distance_from_home": 1, "used_chip": 1}


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self._old = observability._reporter
        observability._reporter = observability._Reporter()

    def tearDown(self):
        observability._reporter.shutdown()
        observability._reporter = self._old

    def test_disabled_is_a_pure_passthrough(self):
        with mock.patch.dict(os.environ, {"MLFLOW_TRACING_ENABLED": "false"}):
            result = observability.trace_scoring(VALUES, good_scorer)
        self.assertEqual(result["score"], 0.7)
        self.assertIsNone(observability._reporter._thread)

    def test_enabled_logs_trace_metrics_and_artifact(self):
        record = new_record()
        env = {"MLFLOW_TRACING_ENABLED": "true", "MLFLOW_TRACKING_URI": "file:///tmp/fake-mlruns"}
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, build_fake_mlflow(record)):
            observability.warm_up()
            self.assertTrue(wait_for(observability._reporter.ready.is_set))
            for _ in range(3):
                self.assertEqual(
                    observability.trace_scoring(VALUES, good_scorer, request_id="abc")["score"], 0.7)
            self.assertTrue(wait_for(lambda: observability._reporter.processed >= 3))
            observability._reporter.shutdown()

        keys = {m.key for m in record["metrics"]}
        self.assertTrue({"prediction_score", "scoring_latency_ms", "flagged_rate",
                         "score_margin", "predictions_total"} <= keys)
        self.assertEqual(record["spans"].count(observability.SPAN_NAME), 3)
        self.assertEqual(record["span_outputs"][0]["mode"], "heuristic_demo")
        self.assertEqual(record["span_inputs"][0]["feature_names"], ["distance_from_home", "used_chip"])
        self.assertEqual(record["tags"]["scorer_mode"], "heuristic_demo")
        self.assertEqual(record["artifacts"][-1][0], "monitoring/summary.json")
        self.assertEqual(record["artifacts"][-1][1]["predictions_total"], 3)
        self.assertEqual(record["terminated"], ["FINISHED"])
        # privacy: no raw values anywhere in what was sent
        self.assertNotIn("distance_from_home=1", str(record))

    def test_scoring_error_is_traced_and_reraised(self):
        record = new_record()
        env = {"MLFLOW_TRACING_ENABLED": "true", "MLFLOW_TRACKING_URI": "file:///tmp/fake-mlruns"}
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, build_fake_mlflow(record)):
            observability.warm_up()
            self.assertTrue(wait_for(observability._reporter.ready.is_set))
            with self.assertRaises(ValueError):
                observability.trace_scoring(VALUES, failing_scorer)
            self.assertTrue(wait_for(lambda: observability._reporter.processed >= 1))
            observability._reporter.shutdown()
        self.assertEqual(record["span_errors"], ["ValueError"])
        self.assertIn("scoring_errors_total", {m.key for m in record["metrics"]})

    def test_missing_mlflow_never_breaks_scoring(self):
        env = {"MLFLOW_TRACING_ENABLED": "true", "MLFLOW_TRACKING_URI": "file:///tmp/fake-mlruns"}
        with mock.patch.dict(os.environ, env), mock.patch.dict(sys.modules, {"mlflow": None}):
            self.assertEqual(observability.trace_scoring(VALUES, good_scorer)["score"], 0.7)
            self.assertTrue(wait_for(lambda: observability._reporter.last_error is not None))
        self.assertIn("not installed", observability._reporter.last_error)
        self.assertFalse(observability._reporter.ready.is_set())

    def test_unreachable_server_is_reported_and_scoring_unaffected(self):
        env = {"MLFLOW_TRACING_ENABLED": "true", "MLFLOW_TRACKING_URI": "http://127.0.0.1:9"}
        with mock.patch.dict(os.environ, env):
            self.assertEqual(observability.trace_scoring(VALUES, good_scorer)["score"], 0.7)
            self.assertTrue(wait_for(lambda: observability._reporter.last_error is not None))
        self.assertIn("cannot reach MLflow server", observability._reporter.last_error)

    def test_localhost_uri_on_render_gets_a_clear_error(self):
        env = {"MLFLOW_TRACING_ENABLED": "true", "RENDER": "true"}
        with mock.patch.dict(os.environ, env):
            os.environ.pop("MLFLOW_TRACKING_URI", None)
            observability.warm_up()
            self.assertTrue(wait_for(lambda: observability._reporter.last_error is not None))
        self.assertIn("Render container itself", observability._reporter.last_error)

    def test_redact_uri_removes_credentials(self):
        self.assertEqual(observability.redact_uri("https://user:secret@host.example.com:8443/x?a=1"),
                         "https://host.example.com:8443/x")


if __name__ == "__main__":
    unittest.main()
