"""cStat 655: a Ciência foi recusada porque a NF-e JÁ tem manifestação final.

O 655 caía no "else" genérico: a nota ia para "erro de manifestação" e o botão
de Ciência continuava ali. Cada clique reenviava o 210210 e voltava 655 — para
sempre —, e o XML completo nunca era buscado. A nota não está com erro: ela já
foi manifestada (Confirmação, Desconhecimento ou Operação não Realizada).
"""
import datetime
from unittest.mock import MagicMock, patch

import pytest
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.inbound_nfe.models import InboundNFe, NFeEvent, NFeManifestation
from apps.inbound_nfe.services.manifestation import register_science
from apps.invoices.models import FiscalConfig

pytestmark = pytest.mark.django_db

CHAVE = "33261056228356003157550380002835131951652290"
MANIFESTAR = "apps.inbound_nfe.services.manifestation.manifest_nfe"
BUSCAR_XML = "apps.inbound_nfe.services.manifestation.fetch_full_xml"
ENFILEIRAR = "apps.inbound_nfe.tasks.fetch_full_xml_task.delay"


def _resposta(event_cstat, reason, protocol=""):
    resp = MagicMock()
    resp.batch_cstat, resp.batch_reason = "128", "Lote de Evento Processado"
    resp.event_cstat, resp.event_reason, resp.protocol = event_cstat, reason, protocol
    resp.registered_at = datetime.datetime.now(datetime.timezone.utc)
    resp.raw_xml, resp.request_xml = "<ret/>", "<req/>"
    resp.is_success = event_cstat in ("135", "136", "573")
    return resp


RESPOSTA_655 = _resposta(
    "655", "Rejeicao: Evento de Ciencia da Operacao informado apos a manifestacao final do destinatario")


@pytest.fixture
def contexto_tenant(account):
    with tenant_context(account):
        yield account


@pytest.fixture
def nota(account, restaurant):
    FiscalConfig.objects.create(account=account, restaurant=restaurant, cnpj="12345678000190",
                                certificate_password="x", uf="RJ")
    return InboundNFe.objects.create(
        account=account, restaurant=restaurant, access_key=CHAVE, status=InboundNFe.STATUS_SUMMARY,
        xml_status=InboundNFe.XML_STATUS_SUMMARY_ONLY, manifestation_status=InboundNFe.MANIFEST_NONE)


def test_655_nao_e_erro_a_nota_ja_tem_manifestacao_final(nota):
    with patch(MANIFESTAR, return_value=RESPOSTA_655), \
            patch(BUSCAR_XML, return_value=False) as buscar, patch(ENFILEIRAR) as enfileirar:
        ok, mensagem = register_science(nota)

    tentativa = NFeManifestation.all_objects.get(invoice=nota, event_code="210210")
    assert tentativa.status == NFeManifestation.STATUS_REJECTED
    assert (tentativa.sefaz_batch_status, tentativa.sefaz_event_status) == ("128", "655")
    assert "manifestacao final" in tentativa.sefaz_event_reason
    nota.refresh_from_db()
    assert nota.manifestation_status == InboundNFe.MANIFEST_FINAL_EXISTS
    assert nota.xml_status == InboundNFe.XML_STATUS_FULL_XML_PENDING
    assert ok and "manifestação final" in mensagem
    buscar.assert_called_once_with(nota)
    enfileirar.assert_called_once_with(str(nota.id))


def test_655_com_o_xml_ja_baixado_nao_volta_para_pendente(nota):
    nota.xml_status = InboundNFe.XML_STATUS_FULL_XML_AVAILABLE
    nota.save(update_fields=["xml_status"])

    with patch(MANIFESTAR, return_value=RESPOSTA_655), patch(BUSCAR_XML) as buscar:
        register_science(nota)

    nota.refresh_from_db()
    assert nota.xml_status == InboundNFe.XML_STATUS_FULL_XML_AVAILABLE
    buscar.assert_not_called()


@pytest.mark.parametrize("evento, estado", [
    ("210200", InboundNFe.MANIFEST_CONFIRMED),
    ("210220", InboundNFe.MANIFEST_UNKNOWN),
    ("210240", InboundNFe.MANIFEST_NOT_PERFORMED),
])
def test_655_reconcilia_com_o_evento_final_que_chegou_da_distribuicao(nota, evento, estado):
    NFeEvent.all_objects.create(
        account=nota.account, restaurant=nota.restaurant, access_key=CHAVE, event_code=evento,
        sequence=1, event_datetime=timezone.now(), sefaz_cstat="135")

    with patch(MANIFESTAR, return_value=RESPOSTA_655), patch(BUSCAR_XML, return_value=True):
        register_science(nota)

    nota.refresh_from_db()
    assert nota.manifestation_status == estado


def test_segundo_clique_depois_do_655_nao_reenvia_a_ciencia(nota, api_client, contexto_tenant):
    with patch(MANIFESTAR, return_value=RESPOSTA_655) as manifestar, \
            patch(BUSCAR_XML, return_value=True):
        register_science(nota)
        resposta = api_client.post(f"/api/v1/inbound-nfe/{nota.id}/register-science/")

    assert manifestar.call_count == 1
    assert resposta.status_code == 200, resposta.content
    corpo = resposta.json()
    assert corpo["success"] is True and corpo["science_sent"] is False
    assert corpo["reason"] == "final_manifestation_already_exists"
    assert corpo["message"] == "A NF-e já possui uma manifestação final registrada."


@pytest.mark.parametrize("estado", [
    InboundNFe.MANIFEST_CONFIRMED, InboundNFe.MANIFEST_UNKNOWN, InboundNFe.MANIFEST_NOT_PERFORMED])
def test_nota_ja_manifestada_nao_envia_ciencia(nota, estado):
    nota.manifestation_status = estado
    nota.save(update_fields=["manifestation_status"])

    with patch(MANIFESTAR) as manifestar:
        ok, _ = register_science(nota)

    assert ok
    manifestar.assert_not_called()
    nota.refresh_from_db()
    assert nota.manifestation_status == estado


def test_135_continua_registrando_a_ciencia(nota):
    with patch(MANIFESTAR, return_value=_resposta("135", "Evento registrado", "135260000999")), \
            patch(BUSCAR_XML, return_value=True):
        ok, _ = register_science(nota)

    assert ok
    nota.refresh_from_db()
    assert nota.manifestation_status == InboundNFe.MANIFEST_SCIENCE_REGISTERED
    assert NFeManifestation.all_objects.get(invoice=nota).status == NFeManifestation.STATUS_ACCEPTED


def test_outra_rejeicao_continua_virando_erro_de_manifestacao(nota):
    with patch(MANIFESTAR, return_value=_resposta("650", "Rejeicao: Evento de Ciencia ja registrado")), \
            patch(BUSCAR_XML) as buscar:
        ok, mensagem = register_science(nota)

    assert not ok and "650" in mensagem
    nota.refresh_from_db()
    assert nota.manifestation_status == InboundNFe.MANIFEST_ERROR
    buscar.assert_not_called()
