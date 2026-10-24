"""Validated input form for the seven transaction features."""
import math
from django import forms


def validate_finite(value):
    if not math.isfinite(value):
        raise forms.ValidationError("Enter a finite number.")


class TransactionForm(forms.Form):
    distance_from_home = forms.FloatField(
        min_value=0, validators=[validate_finite], label="Distance from home (km)", initial=8.0
    )
    distance_from_last_transaction = forms.FloatField(
        min_value=0, validators=[validate_finite], label="Distance from last transaction (km)", initial=1.2
    )
    ratio_to_median_purchase_price = forms.FloatField(
        min_value=0, validators=[validate_finite], label="Purchase price / median ratio", initial=1.0
    )
    repeat_retailer = forms.ChoiceField(choices=[("1", "Yes"), ("0", "No")], label="Repeat retailer")
    used_chip = forms.ChoiceField(choices=[("1", "Yes"), ("0", "No")], label="Chip used")
    used_pin_number = forms.ChoiceField(choices=[("1", "Yes"), ("0", "No")], label="PIN used")
    online_order = forms.ChoiceField(choices=[("1", "Yes"), ("0", "No")], label="Online order")
