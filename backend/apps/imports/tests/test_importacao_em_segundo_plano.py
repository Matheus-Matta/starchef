"""Importação de planilha processada pelo worker, sem prender a tela.

A tela mandava uma requisição por linha e esperava cada uma. Agora o
`POST /imports/` responde na hora (202) e o worker processa pela MESMA view
da tela — mesma validação, mesmas permissões, mesmo restaurante.
"""
from unittest import mock

import pytest

from apps.core.tenant import tenant_context
from apps.imports.models import ImportJob
from apps.imports.services import run_import
from apps.menu.models import ProductCategory
from apps.notifications.models import Notification

pytestmark = pytest.mark.django_db
ROTA = "/api/v1/imports/"


def _pedir(cliente, linhas, **extra):
    return cliente.post(ROTA, {"endpoint": "/menu/categories/", "key": "name", "rows": linhas, **extra},
                        format="json", HTTP_X_RESTAURANT_ID=extra.pop("restaurante", ""))


def test_responde_na_hora_e_entrega_ao_worker(admin_client, restaurant, django_capture_on_commit_callbacks):
    with mock.patch("apps.imports.tasks.run_import_task.delay") as enfileirar:
        with django_capture_on_commit_callbacks(execute=True):
            resposta = _pedir(admin_client, [{"name": "Bebidas", "restaurant": str(restaurant.pk)}])

    assert resposta.status_code == 202, resposta.data
    assert resposta.data["status"] == ImportJob.STATUS_QUEUED
    enfileirar.assert_called_once_with(resposta.data["id"])
    with tenant_context(restaurant.account):
        assert not ProductCategory.objects.filter(name="Bebidas").exists()  # nada gravado ainda


def test_worker_cria_atualiza_pela_chave_e_segue_depois_de_um_erro(
    admin_client, admin_user, account, restaurant,
):
    with tenant_context(account):
        existente = ProductCategory.objects.create(account=account, restaurant=restaurant, name="Lanches",
                                                   display_order=1)
    with mock.patch("apps.imports.tasks.run_import_task.delay"):
        job_id = _pedir(admin_client, [
            {"name": "Bebidas", "restaurant": str(restaurant.pk)},
            {"name": "LANCHES", "display_order": 9},  # mesma chave: atualiza
            {"name": "", "restaurant": str(restaurant.pk)},  # inválida: não para as outras
            {"name": "Sobremesas", "restaurant": str(restaurant.pk)},
        ]).data["id"]

    job = run_import(job_id)

    assert job.status == ImportJob.STATUS_DONE
    assert (job.created_count, job.updated_count) == (2, 1)
    assert len(job.errors) == 1 and job.errors[0].startswith("Linha 4:")
    with tenant_context(account):
        existente.refresh_from_db()
        assert existente.display_order == 9
        assert ProductCategory.objects.filter(name__in=["Bebidas", "Sobremesas"]).count() == 2
    aviso = Notification.all_objects.get(recipient=admin_user, entity="imports.ImportJob")
    assert "2 criado(s), 1 atualizado(s)" in aviso.body
    assert job.rows == []  # a planilha não fica guardada depois de processada
    assert run_import(job_id) is None  # já processada: não roda de novo


@pytest.mark.parametrize("endpoint", ["/reports/sales/", "/menu/categories/../", "menu/categories/", "/nao-existe/"])
def test_rota_que_nao_aceita_importacao_e_recusada(admin_client, endpoint):
    resposta = admin_client.post(ROTA, {"endpoint": endpoint, "rows": [{"name": "x"}]}, format="json")
    assert resposta.status_code == 400


def test_chave_que_nao_e_campo_e_recusada(admin_client):
    resposta = admin_client.post(ROTA, {"endpoint": "/menu/categories/", "key": "id; drop", "rows": [{}]},
                                 format="json")
    assert resposta.status_code == 400


def test_cada_um_ve_so_a_propria_importacao(admin_client, api_client):
    with mock.patch("apps.imports.tasks.run_import_task.delay"):
        job_id = _pedir(admin_client, [{"name": "X"}]).data["id"]

    assert admin_client.get(f"{ROTA}{job_id}/").status_code == 200
    assert api_client.get(f"{ROTA}{job_id}/").status_code == 404
