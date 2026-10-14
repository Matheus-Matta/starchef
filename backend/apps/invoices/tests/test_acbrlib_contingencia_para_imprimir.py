# O fixture `ambiente` vem importado do teste do provedor; o pytest o injeta
# pelo nome do parâmetro, e o ruff lê isso como redefinição.
# ruff: noqa: F811
"""Na ACBrLib, o cliente não sai sem cupom (pedido do dono da loja, 2026-10-13).

Com a contingência offline ligada, além da SEFAZ fora do ar, também entram em
contingência (assinada e impressa na hora):

* a nota RECUSADA pela SEFAZ — o cupom sai, e a recusa fica para corrigir e
  emitir de novo depois;
* o tempo ESGOTADO e a nota que ficou "aguardando autorização" — aqui a nota
  normal PODE ter sido autorizada. A chave dela fica guardada
  (`chave_normal`) e, antes de transmitir a contingência, ela é CONSULTADA:
  autorizada, vale ela e a contingência é descartada (sem nota em dobro);
  desconhecida, a contingência é transmitida.

Erro de cadastro (certificado, CSC) não entra: sem certificado nem a
contingência se assina.
"""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.services import (
    is_fiscally_printable,
    reprocess_pending_fiscal_invoices,
    resend_fiscal_invoice,
)
from apps.invoices.tests.test_acbrlib_provider import (  # noqa: F401 — fixture
    XML,
    Comunicador,
    _resposta,
    ambiente,
)

pytestmark = pytest.mark.django_db

CHAVE_CONTINGENCIA = "3" * 44


class ComunicadorComConsulta(Comunicador):
    """O falso de sempre, mais "processando" e a consulta pela chave."""

    def __init__(self, sefaz="online", consulta="nao_encontrada"):
        super().__init__(sefaz)
        self.consulta = consulta

    def __call__(self, metodo, url, json=None, headers=None, timeout=None):
        rota = url.split("acbr.local")[1]
        if rota == "/v1/nfe/consultar":
            self.chamadas.append((rota, json))
            if self.consulta == "autorizada":
                return _resposta(200, {"situacao": "autorizada", "cstat": 100, "motivo": "Autorizado",
                                       "chave": json["chave"], "protocolo": "135999",
                                       "recebido_em": "2026-10-13T10:00:00-03:00"})
            return _resposta(200, {"situacao": "nao_encontrada", "cstat": 217, "motivo": "Não consta"})
        if rota == "/v1/nfe/emitir" and json["tp_emis"] == "1" and self.sefaz == "processando":
            self.chamadas.append((rota, json))
            return _resposta(200, {"situacao": "processando", "cstat": 105, "motivo": "Em processamento"})
        return super().__call__(metodo, url, json=json, headers=headers, timeout=timeout)


def _com_contingencia(ambiente):
    ambiente.config.offline_contingency = True
    ambiente.config.save()


def _emitir(ambiente, monkeypatch, comunicador):
    from apps.invoices.services import emit_fiscal_invoice

    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    return emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)


def _contingencia_impressa(nota):
    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY
    assert nota.status == Invoice.STATUS_PENDING
    assert nota.fiscal_payload["awaiting"] == "transmission"
    assert nota.access_key == CHAVE_CONTINGENCIA and nota.xml_content == XML
    assert is_fiscally_printable(nota)


def test_recusa_da_sefaz_sai_em_contingencia_e_guarda_o_motivo(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("recusa"))

    _contingencia_impressa(nota)
    assert "NCM inexistente" in nota.fiscal_payload["contingency_reason"]
    # Recusada não existe na SEFAZ: não há nota normal a consultar depois.
    assert "chave_normal" not in nota.fiscal_payload


def test_tempo_esgotado_sai_em_contingencia_guardando_a_chave_normal(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("timeout_so_na_normal"))

    _contingencia_impressa(nota)
    assert len(nota.fiscal_payload["chave_normal"]) == 44
    assert nota.fiscal_payload["chave_normal"] != CHAVE_CONTINGENCIA


def test_aguardando_autorizacao_sai_em_contingencia(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))

    _contingencia_impressa(nota)
    assert nota.fiscal_payload["chave_normal"]


def test_sem_contingencia_ligada_nada_muda(ambiente, monkeypatch):
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("recusa"))

    assert nota.status == Invoice.STATUS_ERROR
    assert nota.emission_type == Invoice.EMISSION_NORMAL


def test_normal_autorizada_descarta_a_contingencia_sem_transmitir(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))
    chave_normal = nota.fiscal_payload["chave_normal"]

    comunicador = ComunicadorComConsulta("online", consulta="autorizada")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    reprocess_pending_fiscal_invoices()

    nota.refresh_from_db()
    assert [rota for rota, _ in comunicador.chamadas] == ["/v1/nfe/consultar"]
    assert comunicador.chamadas[0][1]["chave"] == chave_normal
    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.access_key == chave_normal
    assert nota.emission_type == Invoice.EMISSION_NORMAL
    assert nota.fiscal_payload["contingencia_descartada"] == CHAVE_CONTINGENCIA


def test_normal_desconhecida_transmite_a_contingencia(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("processando"))

    comunicador = ComunicadorComConsulta("online", consulta="nao_encontrada")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    reprocess_pending_fiscal_invoices()

    nota.refresh_from_db()
    assert [rota for rota, _ in comunicador.chamadas] == ["/v1/nfe/consultar", "/v1/nfe/transmitir"]
    assert nota.status == Invoice.STATUS_ISSUED
    assert "chave_normal" not in nota.fiscal_payload


def test_contingencia_recusada_de_novo_reemite_normal_depois_de_corrigir(ambiente, monkeypatch):
    _com_contingencia(ambiente)
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta("recusa"))
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", ComunicadorComConsulta("recusa"))
    reprocess_pending_fiscal_invoices()
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_ERROR

    # O operador corrige o cadastro e reenvia: o XML recusado não serve mais —
    # sai uma nota normal nova, não a mesma contingência outra vez.
    comunicador = ComunicadorComConsulta("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    nota = resend_fiscal_invoice(nota, user=ambiente.user)

    rota, corpo = comunicador.chamadas[0]
    assert rota == "/v1/nfe/emitir" and corpo["tp_emis"] == "1"
    assert nota.status == Invoice.STATUS_ISSUED
    assert nota.emission_type == Invoice.EMISSION_NORMAL
