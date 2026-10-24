
"""HTTP views for the transaction anomaly dashboard and operational probes."""

import hmac
import logging
import os

from django.db import DatabaseError, connection
from django.http import Http404, JsonResponse
from django.shortcuts import render

from .forms import TransactionForm
from .models import PredictionLog
from .observability import get_status, record_issue, trace_scoring, warm_up
from .services import ScoringError, score_transaction


logger = logging.getLogger(__name__)


def dashboard(request):
    result = None
    form = TransactionForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        values = form.cleaned_data.copy()

        for key in (
            "repeat_retailer",
            "used_chip",
            "used_pin_number",
            "online_order",
        ):
            values[key] = int(values[key])

        try:
            result = trace_scoring(
                values,
                score_transaction,
                request_id=getattr(request, "request_id", None),
            )

            PredictionLog.objects.create(
                score=result["score"],
                threshold=result["threshold"],
                flagged=result["flagged"],
                mode=result["mode"],
            )

        except (ScoringError, ValueError):
            logger.exception(
                "transaction_scoring_failed request_id=%s",
                getattr(request, "request_id", "unknown"),
            )
            form.add_error(
                None,
                "Scoring is temporarily unavailable. Please try again later.",
            )
            result = None

        except DatabaseError:
            logger.exception(
                "prediction_history_write_failed request_id=%s",
                getattr(request, "request_id", "unknown"),
            )
            record_issue("prediction_history_write_failed")
            form.add_error(
                None,
                "The score was calculated, but prediction history could not be saved.",
            )

    try:
        recent = PredictionLog.objects.order_by("-created_at")[:6]
        total = PredictionLog.objects.count()
        flagged_count = PredictionLog.objects.filter(flagged=True).count()

    except DatabaseError:
        logger.exception(
            "prediction_history_unavailable request_id=%s",
            getattr(request, "request_id", "unknown"),
        )
        record_issue("prediction_history_unavailable")
        recent, total, flagged_count = [], 0, 0
        form.add_error(
            None,
            "Prediction history is temporarily unavailable.",
        )

    return render(
        request,
        "detector/dashboard.html",
        {
            "form": form,
            "result": result,
            "recent": recent,
            "total": total,
            "flagged_count": flagged_count,
        },
    )


def health(request):
    """Liveness probe: confirms the Django process can answer HTTP requests."""
    warm_up()
    return JsonResponse(
        {
            "status": "ok",
            "service": "transaction-anomaly-dashboard",
        }
    )


def ready(request):
    """Readiness probe: verifies the configured database can answer a query."""
    try:
        connection.ensure_connection()
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

    except DatabaseError:
        logger.exception(
            "readiness_check_failed request_id=%s",
            getattr(request, "request_id", "unknown"),
        )
        return JsonResponse(
            {
                "status": "not_ready",
                "checks": {"database": "failed"},
            },
            status=503,
        )

    return JsonResponse(
        {
            "status": "ready",
            "checks": {"database": "ok"},
        }
    )


def observability_status(request):
    """Return observability diagnostics only when a configured token is supplied.

    Supply the token in the X-Status-Token header (preferred) or ?token=...
    """
    expected = os.environ.get("OBSERVABILITY_STATUS_TOKEN", "").strip()
    supplied = (
        request.headers.get("X-Status-Token")
        or request.GET.get("token", "")
    )

    if not expected or not hmac.compare_digest(
        supplied.encode(),
        expected.encode(),
    ):
        raise Http404

    return JsonResponse(get_status())
