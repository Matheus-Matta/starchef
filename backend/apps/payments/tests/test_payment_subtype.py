"""Regras de subtipo de cartão no pagamento (Sprint 6 · STC-061)."""
import pytest
from rest_framework.exceptions import ValidationError

from apps.payments.models import Payment, PaymentMethod
from apps.payments.serializers import PaymentSerializer

pytestmark = pytest.mark.django_db


def _method(account, restaurant, branch, method_type, name):
    return PaymentMethod.objects.create(account=account, restaurant=restaurant, branch=branch, name=name, method_type=method_type)


def test_card_requires_subtype(account, restaurant, branch):
    card = _method(account, restaurant, branch, PaymentMethod.TYPE_CARD, "Cartão")
    serializer = PaymentSerializer()
    with pytest.raises(ValidationError):
        serializer.validate({"payment_method": card, "card_subtype": ""})


def test_card_with_subtype_ok(account, restaurant, branch):
    card = _method(account, restaurant, branch, PaymentMethod.TYPE_CARD, "Cartão")
    serializer = PaymentSerializer()
    result = serializer.validate({"payment_method": card, "card_subtype": Payment.CARD_DEBIT})
    assert result["card_subtype"] == "debit"


def test_non_card_rejects_subtype(account, restaurant, branch):
    pix = _method(account, restaurant, branch, PaymentMethod.TYPE_PIX, "PIX")
    serializer = PaymentSerializer()
    with pytest.raises(ValidationError):
        serializer.validate({"payment_method": pix, "card_subtype": Payment.CARD_CREDIT})


def test_non_card_without_subtype_ok(account, restaurant, branch):
    cash = _method(account, restaurant, branch, PaymentMethod.TYPE_CASH, "Dinheiro")
    serializer = PaymentSerializer()
    result = serializer.validate({"payment_method": cash, "card_subtype": ""})
    assert result["card_subtype"] == ""
