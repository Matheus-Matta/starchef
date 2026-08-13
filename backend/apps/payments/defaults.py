"""Provisionamento idempotente das formas de pagamento operacionais."""

from apps.payments.models import PaymentMethod


DEFAULT_PAYMENT_METHODS = (
    ("Dinheiro", PaymentMethod.TYPE_CASH),
    ("Cartao de credito", PaymentMethod.TYPE_CARD),
    ("Cartao de debito", PaymentMethod.TYPE_CARD),
    ("PIX", PaymentMethod.TYPE_PIX),
)


def ensure_default_payment_methods(*, restaurant, branch=None):
    """Cria os métodos padrão assim que a conta recebe seu restaurante."""
    branch = branch or restaurant.branches.filter(deleted_at__isnull=True).first()
    return [
        PaymentMethod.all_objects.get_or_create(
            account=restaurant.account,
            restaurant=restaurant,
            branch=branch,
            name=name,
            defaults={"method_type": method_type, "is_active": True},
        )[0]
        for name, method_type in DEFAULT_PAYMENT_METHODS
    ]
