"""Catálogo de permissões + vínculo com Perfil de acesso (Role)."""
import pytest
from django.apps import apps
from django.db.models.signals import post_migrate

from apps.accounts.models import Permission, Role
from apps.accounts.permission_catalog import ALL_CODES

pytestmark = pytest.mark.django_db


@pytest.fixture
def permissions(db):
    return [
        Permission.objects.update_or_create(code="menu.manage", defaults={"name": "Gerenciar cardápio"})[0],
        Permission.objects.update_or_create(code="orders.view", defaults={"name": "Visualizar pedidos"})[0],
    ]


def test_post_migrate_populates_canonical_permission_catalog(db):
    Permission.objects.all().delete()
    app_config = apps.get_app_config("accounts")

    post_migrate.send(sender=app_config, app_config=app_config, verbosity=0)

    assert set(Permission.objects.values_list("code", flat=True)) == set(ALL_CODES)


def test_permissions_endpoint_lists_catalog(admin_client, permissions):
    resp = admin_client.get("/api/v1/permissions/")
    assert resp.status_code == 200, resp.data
    codes = [p["code"] for p in resp.data]
    assert "menu.manage" in codes
    assert "orders.view" in codes


def test_roles_endpoint_is_read_only(admin_client, permissions):
    """Perfis de Acesso agora sao fixos: a API nao aceita mais criar/editar/apagar."""
    payload = {
        "name": "Gerente VIP",
        "code": "gerente-vip",
        "permissions": [str(permissions[0].id), str(permissions[1].id)],
    }
    resp = admin_client.post("/api/v1/roles/", payload, format="json")
    assert resp.status_code == 405, resp.data
    assert not Role.all_objects.filter(code="gerente-vip").exists()


def test_roles_endpoint_lists_fixed_roles(admin_client):
    resp = admin_client.get("/api/v1/roles/")
    assert resp.status_code == 200, resp.data
    rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
    codes = {row["code"] for row in rows}
    assert {"waiter", "cashier", "manager", "admin"} <= codes


def test_account_creation_provisions_fixed_system_roles(account):
    """`Account.objects.create` (signal) provisiona os 4 perfis fixos sozinho."""
    from apps.accounts.role_catalog import SYSTEM_ROLE_CODES

    roles = {role.code: role for role in Role.all_objects.filter(account=account)}
    assert set(roles) == set(SYSTEM_ROLE_CODES)
    assert all(role.is_system for role in roles.values())

    admin_codes = set(roles["admin"].permissions.values_list("code", flat=True))
    assert admin_codes == set(ALL_CODES)
    assert roles["admin"].is_account_admin is True

    waiter_codes = set(roles["waiter"].permissions.values_list("code", flat=True))
    cashier_codes = set(roles["cashier"].permissions.values_list("code", flat=True))
    manager_codes = set(roles["manager"].permissions.values_list("code", flat=True))

    # Hierarquia pedida: garçom ⊂ caixa ⊂ gerente ⊂ admin.
    assert waiter_codes <= cashier_codes <= manager_codes <= admin_codes
    assert "orders.view" in cashier_codes and "orders.view" not in waiter_codes
    assert "payments.manage" in cashier_codes
    assert "devices.manage" in manager_codes and "devices.manage" not in cashier_codes
