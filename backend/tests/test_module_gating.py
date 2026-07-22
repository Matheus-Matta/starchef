"""Testa o licenciamento modular: APIs de modulos desabilitados retornam 403."""
import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.core.modules import OPTIONAL_MODULES

# (endpoint, modulo exigido) — base sempre passa; opcionais dependem da conta.
OPTIONAL_ENDPOINTS = [
    ("/api/v1/menu/menus/", "ecommerce"),
    ("/api/v1/delivery/zones/", "entrega"),
    ("/api/v1/delivery/deliverymen/", "entrega"),
    ("/api/v1/payments/", "financeiro"),
    ("/api/v1/invoices/", "financeiro"),
    ("/api/v1/stock/locations/", "logistica"),
    ("/api/v1/stock/movements/", "logistica"),
]


def _auth(api_client, user):
    """Autentica com JWT real (o TenantMiddleware exige token para resolver a conta)."""
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")


@pytest.mark.django_db
def test_base_endpoints_always_accessible(api_client, manager_user):
    _auth(api_client, manager_user)
    # Conta sem modulos opcionais (default) — base continua liberado.
    assert api_client.get("/api/v1/orders/").status_code == 200
    assert api_client.get("/api/v1/menu/products/").status_code == 200
    assert api_client.get("/api/v1/tables/").status_code == 200


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint,module", OPTIONAL_ENDPOINTS)
def test_optional_endpoint_blocked_without_module(api_client, manager_user, endpoint, module):
    _auth(api_client, manager_user)
    response = api_client.get(endpoint)
    assert response.status_code == 403, f"{endpoint} deveria bloquear sem o modulo {module}"


@pytest.mark.django_db
@pytest.mark.parametrize("endpoint,module", OPTIONAL_ENDPOINTS)
def test_optional_endpoint_allowed_with_module(api_client, account, manager_user, endpoint, module):
    account.enabled_modules = list(OPTIONAL_MODULES)
    account.save(update_fields=["enabled_modules"])
    _auth(api_client, manager_user)
    response = api_client.get(endpoint)
    assert response.status_code == 200, f"{endpoint} deveria liberar com o modulo {module}"


@pytest.mark.django_db
def test_delivery_orders_native_in_base(api_client, restaurant, branch, manager_user):
    """Regra critica: pedido de delivery pode ser criado no Base, sem o modulo Entrega."""
    _auth(api_client, manager_user)
    response = api_client.post(
        "/api/v1/orders/",
        {"order_type": "delivery", "restaurant": str(restaurant.id), "branch": str(branch.id)},
        format="json",
    )
    assert response.status_code == 201, response.data
    # Mas a gestao de entregadores (Entrega) continua bloqueada.
    assert api_client.get("/api/v1/delivery/deliverymen/").status_code == 403


@pytest.mark.django_db
def test_superuser_bypasses_module_gating(api_client, db):
    from django.contrib.auth import get_user_model

    root = get_user_model().objects.create_superuser("root", "root@starchef.test", "secret123")
    _auth(api_client, root)
    # Superuser (dono da plataforma) acessa qualquer modulo mesmo sem conta.
    assert api_client.get("/api/v1/stock/locations/").status_code == 200
