from django.http import JsonResponse
from django.shortcuts import render
from .forms import TransactionForm
from .models import PredictionLog
from .services import score_transaction

def dashboard(request):
    result = None
    if request.method == "POST":
        form = TransactionForm(request.POST)
        if form.is_valid():
            values = form.cleaned_data.copy()
            for key in ("repeat_retailer", "used_chip", "used_pin_number", "online_order"):
                values[key] = int(values[key])
            result = score_transaction(values)
            PredictionLog.objects.create(
                reconstruction_error=result["error"],
                threshold=result["threshold"],
                flagged=result["flagged"],
                mode=result["mode"],
            )
    else:
        form = TransactionForm()
    recent = PredictionLog.objects.order_by("-created_at")[:6]
    total = PredictionLog.objects.count()
    flagged_count = PredictionLog.objects.filter(flagged=True).count()
    return render(request, "detector/dashboard.html", {
        "form": form, "result": result, "recent": recent,
        "total": total, "flagged_count": flagged_count,
    })

def health(request):
    return JsonResponse({"status": "ok", "service": "autoencoder-fraud-dashboard"})
