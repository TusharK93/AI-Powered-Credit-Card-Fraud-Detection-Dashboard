"""Regression tests for scoring, validation, and operational endpoints."""
from django.test import TestCase, override_settings
from .models import PredictionLog
from .services import FEATURES, score_transaction


def sample_values(**overrides):
    values = {
        "distance_from_home": 8,
        "distance_from_last_transaction": 1.2,
        "ratio_to_median_purchase_price": 1,
        "repeat_retailer": 1,
        "used_chip": 1,
        "used_pin_number": 1,
        "online_order": 0,
    }
    values.update(overrides)
    return values


class ScoringServiceTests(TestCase):
    @override_settings()
    def test_heuristic_score_is_bounded(self):
        result = score_transaction(sample_values())
        self.assertGreaterEqual(result["score"], 0)
        self.assertLessEqual(result["score"], 1)
        self.assertEqual(result["mode"], "heuristic_demo")
        self.assertEqual(result["features"], FEATURES)

    def test_high_heuristic_score_is_flagged(self):
        result = score_transaction(sample_values(
            distance_from_home=100,
            distance_from_last_transaction=50,
            ratio_to_median_purchase_price=5,
            repeat_retailer=0,
            used_chip=0,
            used_pin_number=0,
            online_order=1,
        ))
        self.assertEqual(result["score"], 1.0)
        self.assertTrue(result["flagged"])

    def test_rejects_non_binary_flags(self):
        with self.assertRaises(ValueError):
            score_transaction(sample_values(used_chip=2))

    def test_rejects_non_finite_values(self):
        with self.assertRaises(ValueError):
            score_transaction(sample_values(distance_from_home=float("nan")))


class DashboardEndpointTests(TestCase):
    def test_health_endpoint(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIn("X-Request-ID", response.headers)

    def test_readiness_endpoint(self):
        response = self.client.get("/ready/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["checks"]["database"], "ok")

    def test_dashboard_get(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_valid_post_is_logged_without_raw_features(self):
        response = self.client.post("/", data={
            "distance_from_home": "100",
            "distance_from_last_transaction": "50",
            "ratio_to_median_purchase_price": "5",
            "repeat_retailer": "0",
            "used_chip": "0",
            "used_pin_number": "0",
            "online_order": "1",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PredictionLog.objects.count(), 1)
        row = PredictionLog.objects.get()
        self.assertTrue(row.flagged)
        self.assertEqual(row.mode, "heuristic_demo")

    def test_invalid_post_does_not_create_history(self):
        response = self.client.post("/", data={"distance_from_home": "-1"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(PredictionLog.objects.count(), 0)
