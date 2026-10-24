
import logging

from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render

from .forms import TransactionForm
from .models import PredictionLog
from .observability import record_issue, trace_scoring
from .services import ScoringError, score_transaction

logger = logging.getLogger(__name__)


def health(request):
    """Basic health endpoint for Render."""
    return JsonResponse({"status": "ok"}, status=200)


def ready(request):
    return JsonResponse({"status": "ready"}, status=200)


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
                reconstruction_error=result["error"],
                threshold=result["threshold"],
                flagged=result["flagged"],
                mode=result["mode"],
            )

        except (ScoringError, ValueError, KeyError):
            logger.exception(
                "transaction_scoring_failed request_id=%s",
                getattr(request, "request_id", "unknown"),
            )
            result = None
            form.add_error(
                None,
                "Scoring is temporarily unavailable. Please try again later.",
            )

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
