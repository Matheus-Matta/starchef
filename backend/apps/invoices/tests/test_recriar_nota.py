# O fixture `ambiente` vem do teste do provedor; o pytest o injeta pelo nome.
# ruff: noqa: F811
"""Recriar a nota que travou: emitir de novo, do zero, sem duplicar a venda."""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.recriar_nota import NotaNaoRecriavel, recriar_nota
from apps.invoices.tests.test_acbrlib_contingencia_para_imprimir import ComunicadorComConsulta
from apps.invoices.tests.test_acbrlib_provider import XML, Comunicador, ambiente  # noqa: F401

pytestmark = pytest.mark.django_db


def _emitir(ambiente, monkeypatch, comunicador):
    from apps.invoices.services import emit_fiscal_invoice

    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    return emit_fiscal_invoice(ambiente.pedido, user=ambiente.user)


def _contingencia_pendente(ambiente, monkeypatch, sefaz="fora"):
    ambiente.config.offline_contingency = True
    ambiente.config.save()
    nota = _emitir(ambiente, monkeypatch, ComunicadorComConsulta(sefaz))
    assert nota.emission_type == Invoice.EMISSION_CONTINGENCY and nota.status == Invoice.STATUS_PENDING
    return nota


def test_contingencia_vencida_e_recriada_como_nota_normal_com_o_mesmo_numero(ambiente, monkeypatch):
    """Reenviar mandava de novo o XML assinado fora do prazo e voltava recusado.

    Recriar descarta aquele XML e emite a nota normal com a data de agora,
    sem abrir buraco na série (o número nunca foi autorizado).
    """
    nota = _contingencia_pendente(ambiente, monkeypatch)
    numero, cnf_antigo = nota.number, nota.fiscal_payload["cNF"]

    comunicador = Comunicador("online")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    nova = recriar_nota(nota, user=ambiente.user)

    assert nova.pk == nota.pk and nova.status == Invoice.STATUS_ISSUED
    assert nova.emission_type == Invoice.EMISSION_NORMAL and nova.number == numero
    rota, corpo = comunicador.chamadas[0]
    assert rota == "/v1/nfe/emitir" and corpo["tp_emis"] == "1"
    assert nova.fiscal_payload["cNF"] != cnf_antigo
    descartada = nova.fiscal_payload["tentativas_descartadas"][0]
    assert descartada["chave"] == "3" * 44 and descartada["xml"] == XML
    assert descartada["situacao"] == "contingency_pending"


def test_a_tentativa_descartada_fica_no_historico_mesmo_se_a_sefaz_recusar_de_novo(ambiente, monkeypatch):
    """O histórico é da auditoria: não pode sumir porque a nova também falhou."""
    nota = _emitir(ambiente, monkeypatch, Comunicador("recusa"))
    assert nota.status == Invoice.STATUS_ERROR

    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", Comunicador("recusa"))
    nova = recriar_nota(nota, user=ambiente.user)

    assert nova.status == Invoice.STATUS_ERROR
    assert len(nova.fiscal_payload["tentativas_descartadas"]) == 1
    assert "NCM inexistente" in nova.fiscal_payload["tentativas_descartadas"][0]["motivo"]


def test_a_normal_autorizada_do_tempo_esgotado_vale_e_nada_e_emitido_de_novo(ambiente, monkeypatch):
    """A contingência de um tempo esgotado guarda a chave da tentativa normal.

    Se a SEFAZ autorizou aquela, recriar emitiria uma segunda nota para a
    mesma venda. A consulta vem antes, e a nota passa a ser a autorizada.
    """
    nota = _contingencia_pendente(ambiente, monkeypatch, "timeout_so_na_normal")

    comunicador = ComunicadorComConsulta("online", consulta="autorizada")
    monkeypatch.setattr("apps.invoices.acbrlib.cliente.requests.request", comunicador)
    resultado = recriar_nota(nota, user=ambiente.user)

    assert resultado.status == Invoice.STATUS_ISSUED
    assert [rota for rota, _ in comunicador.chamadas] == ["/v1/nfe/consultar"]
    assert "tentativas_descartadas" not in resultado.fiscal_payload


def test_nota_em_conciliacao_nao_e_recriada_antes_da_consulta(ambiente, monkeypatch):
    """Tempo esgotado sem contingência: a SEFAZ pode ter a nota. Recriar duplicaria."""
    nota = _emitir(ambiente, monkeypatch, Comunicador("timeout"))
    assert nota.fiscal_payload["awaiting"] == "reconciliation"

    with pytest.raises(NotaNaoRecriavel, match="Atualize o status"):
        recriar_nota(nota, user=ambiente.user)


def test_recriar_nota_autorizada_pela_api_responde_409_com_o_motivo(ambiente, monkeypatch, api_client, account):
    """Conflito de estado é 409, não 400 (o PDV repete 400 para sempre)."""
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    nota = _emitir(ambiente, monkeypatch, Comunicador("online"))

    resposta = api_client.post(f"/api/v1/invoices/{nota.pk}/recreate/")

    assert resposta.status_code == 409, resposta.content
    assert "cancele" in resposta.json()["error"]["message"]
