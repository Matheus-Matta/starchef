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


def test_create_role_with_permissions(admin_client, permissions):
    payload = {
        "name": "Gerente VIP",
        "code": "gerente-vip",
        "permissions": [str(permissions[0].id), str(permissions[1].id)],
    }
    resp = admin_client.post("/api/v1/roles/", payload, format="json")
    assert resp.status_code == 201, resp.data
    role = Role.all_objects.get(code="gerente-vip")
    assert role.permissions.count() == 2
