"""XML da nota: baixar um, ou o período inteiro num ZIP que vale 24 horas."""
import io
import zipfile
from datetime import datetime, timedelta
from unittest import mock

import pytest
from django.core.files.storage import default_storage
from django.utils import timezone

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import run_bulk_job
from apps.invoices.exportacao_xml_arquivo import limpar_vencidas
from apps.invoices.models import Invoice
from apps.notifications.models import Notification
from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db
URL = "/api/v1/invoices/xml-export/"
FILTRO = {"date_from": "2026-10-01", "date_to": "2026-10-31"}


@pytest.fixture(autouse=True)
def _financeiro_e_midia_temporaria(account, settings, tmp_path):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    settings.MEDIA_ROOT = str(tmp_path)


def _nota(restaurant, branch, user, *, dia=10, status=Invoice.STATUS_ISSUED, xml="<nfeProc/>"):
    pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user)
    chave = f"35{pedido.sequence:042d}"
    return Invoice.all_objects.create(
        account=pedido.account, restaurant=restaurant, branch=branch, order=pedido, status=status,
        number=str(pedido.sequence), access_key=chave, xml_content=xml.replace("/>", f" k='{chave}'/>"),
        issued_at=timezone.make_aware(datetime(2026, 10, dia, 12)),
    )


def _baixar(cliente, url):
    resposta = cliente.get(f"/api/v1{url}")
    assert resposta.status_code == 200, resposta.content
    return zipfile.ZipFile(io.BytesIO(b"".join(resposta.streaming_content)))


def test_poucas_notas_saem_na_hora_com_uma_pasta_por_situacao(api_client, restaurant, branch, manager_user):
    """O contador escritura autorizadas e canceladas; a pendente fica de fora por padrão."""
    autorizada = _nota(restaurant, branch, manager_user)
    cancelada = _nota(restaurant, branch, manager_user, status=Invoice.STATUS_CANCELLED)
    _nota(restaurant, branch, manager_user, status=Invoice.STATUS_PENDING)
    fora_do_periodo = _nota(restaurant, branch, manager_user)
    Invoice.all_objects.filter(pk=fora_do_periodo.pk).update(issued_at=timezone.make_aware(datetime(2026, 9, 30)))

    resposta = api_client.post(URL, FILTRO, format="json")

    assert resposta.status_code == 201, resposta.content
    nomes = sorted(_baixar(api_client, resposta.data["download_url"]).namelist())
    assert f"autorizadas/{autorizada.access_key}.xml" in nomes
    assert f"canceladas/{cancelada.access_key}.xml" in nomes
    assert len(nomes) == 2 and not any("pendentes" in nome for nome in nomes)


def test_muitas_notas_vao_para_o_worker_e_o_sino_leva_a_pagina_do_download(
    api_client, restaurant, branch, manager_user, django_capture_on_commit_callbacks
):
    """Montar o ZIP de um mês inteiro na requisição estourava o tempo dela."""
    for _ in range(3):
        _nota(restaurant, branch, manager_user)

    with mock.patch("apps.invoices.exportacao_xml.LIMITE_NA_HORA", 2), \
            mock.patch("apps.bulk_jobs.tasks.run_bulk_job_task.delay") as enfileirar:
        with django_capture_on_commit_callbacks(execute=True):
            resposta = api_client.post(URL, FILTRO, format="json")

    assert resposta.status_code == 202, resposta.content
    enfileirar.assert_called_once_with(resposta.data["id"])
    run_bulk_job(resposta.data["id"])
    aviso = Notification.all_objects.get(recipient=manager_user, object_id=resposta.data["id"])
    assert aviso.url == f"/notas-fiscais/exportar-xml/{resposta.data['id']}"
    assert "24 horas" in aviso.body
    situacao = api_client.get(f"{URL}{resposta.data['id']}/").data
    assert situacao["result"]["total"] == 3 and len(_baixar(api_client, situacao["download_url"]).namelist()) == 3


def test_nota_com_xml_guardado_na_focus_sempre_vai_para_o_worker(api_client, restaurant, branch, manager_user):
    """Buscar cada XML na Focus é uma chamada externa por nota: nunca na requisição."""
    _nota(restaurant, branch, manager_user, xml="/arquivos/nota.xml")

    with mock.patch("apps.bulk_jobs.services.dispatch_bulk_job"):
        resposta = api_client.post(URL, FILTRO, format="json")

    assert resposta.status_code == 202, resposta.content


def test_zip_vencido_e_recusado_com_410_e_apagado_pela_limpeza(api_client, restaurant, branch, manager_user):
    """O ZIP é temporário: passou de 24 h, some, mesmo que ninguém o tenha baixado."""
    _nota(restaurant, branch, manager_user)
    lote = BulkJob.all_objects.get(pk=api_client.post(URL, FILTRO, format="json").data["id"])
    caminho = lote.result["arquivo"]
    assert default_storage.exists(caminho)
    BulkJob.all_objects.filter(pk=lote.pk).update(finished_at=timezone.now() - timedelta(hours=25))

    assert api_client.get(f"{URL}{lote.pk}/download/").status_code == 410
    assert limpar_vencidas() == 1
    assert not default_storage.exists(caminho)
    assert api_client.get(f"{URL}{lote.pk}/").data["expired"] is True


def test_a_exportacao_de_um_usuario_nao_e_baixada_por_outro(admin_client, api_client, restaurant, branch, manager_user):
    """O XML traz o CPF do consumidor: só quem pediu (ou o administrador) baixa."""
    _nota(restaurant, branch, manager_user)
    lote_id = admin_client.post(URL, FILTRO, format="json").data["id"]

    assert api_client.get(f"{URL}{lote_id}/download/").status_code == 404


def test_periodo_invertido_e_entrada_errada(api_client):
    resposta = api_client.post(URL, {"date_from": "2026-10-31", "date_to": "2026-10-01"}, format="json")
    assert resposta.status_code == 400


def test_baixar_o_xml_de_uma_nota_e_o_motivo_quando_ainda_nao_existe(api_client, restaurant, branch, manager_user):
    nota = _nota(restaurant, branch, manager_user)
    sem_xml = _nota(restaurant, branch, manager_user, status=Invoice.STATUS_ERROR, xml="")

    resposta = api_client.get(f"/api/v1/invoices/{nota.pk}/xml/")
    assert resposta.status_code == 200
    assert resposta["Content-Disposition"] == f'attachment; filename="{nota.access_key}.xml"'
    assert resposta.content.decode() == nota.xml_content

    recusa = api_client.get(f"/api/v1/invoices/{sem_xml.pk}/xml/")
    assert recusa.status_code == 404 and "ainda não tem XML" in recusa.json()["error"]["message"]
