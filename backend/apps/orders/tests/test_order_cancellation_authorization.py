import pytest
from django.contrib.auth.hashers import make_password

from apps.accounts.models import Permission
from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


def _order(restaurant, branch, manager_user):
    return create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )


def test_cancelamento_exige_autorizacao_e_motivo(
    api_client,
    restaurant,
    branch,
    manager_user,
):
    order = _order(restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/cancel/",
        {"reason": "Cliente desistiu"},
        format="json",
    )

    assert response.status_code == 403
    order.refresh_from_db()
    assert order.status == Order.STATUS_OPEN


def test_senha_do_restaurante_cancela_e_registra_motivo(
    api_client,
    restaurant,
    branch,
    manager_user,
):
    restaurant.cash_action_password = make_password("senha-operacao")
    restaurant.save(update_fields=["cash_action_password", "updated_at"])
    order = _order(restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/cancel/",
        {
            "reason": "Cliente desistiu",
            "cash_password": "senha-operacao",
        },
        format="json",
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED
    assert order.cancel_reason == "Cliente desistiu"


def test_usuario_com_permissao_pode_autorizar_cancelamento(
    api_client,
    restaurant,
    branch,
    manager_user,
):
    permission, _ = Permission.objects.get_or_create(
        code="orders.cancel",
        defaults={"name": "Cancelar pedidos"},
    )
    manager_user.profile.specific_permissions.add(permission)
    order = _order(restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/cancel/",
        {
            "reason": "Lançamento incorreto",
            "authorization_username": manager_user.username,
            "authorization_password": "x",
        },
        format="json",
    )

    assert response.status_code == 200
    order.refresh_from_db()
    assert order.status == Order.STATUS_CANCELLED


def test_cancelamento_continua_exigindo_motivo_com_senha_valida(
    api_client,
    restaurant,
    branch,
    manager_user,
):
    restaurant.cash_action_password = make_password("senha-operacao")
    restaurant.save(update_fields=["cash_action_password", "updated_at"])
    order = _order(restaurant, branch, manager_user)

    response = api_client.post(
        f"/api/v1/orders/{order.id}/cancel/",
        {"reason": "", "cash_password": "senha-operacao"},
        format="json",
    )

    assert response.status_code == 400
    order.refresh_from_db()
    assert order.status == Order.STATUS_OPEN
