"""Smoke tests do app printers/scales. `CanUseOrManageDevices` exige perfil
admin/owner ou permissão dedicada para GET — usa `admin_client` para não
depender de permissões extra que um gerente comum não tem por padrão.
"""
import pytest

pytestmark = pytest.mark.django_db


def test_printers_list_ok(admin_client):
    resp = admin_client.get("/api/v1/printers/")
    assert resp.status_code == 200


def test_print_jobs_list_ok(admin_client):
    resp = admin_client.get("/api/v1/print-jobs/")
    assert resp.status_code == 200


def test_scales_list_ok(admin_client):
    resp = admin_client.get("/api/v1/scales/")
    assert resp.status_code == 200


def test_scale_readings_list_ok(admin_client):
    resp = admin_client.get("/api/v1/scales/readings/")
    assert resp.status_code == 200
