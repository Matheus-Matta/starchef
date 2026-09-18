"""Uma nota que não saiu tem de dizer POR QUE — sempre.

O defeito que isto fecha: `with_fiscal_state` marcava `emitted: False` numa
nota recusada mas não mandava `message`. O PDV, sem nada para mostrar, caía num
texto fixo — "o provedor fiscal não está configurado" — que ele inventava. O
operador lia essa frase com o provedor configurado e funcionando, em QUALQUER
recusa: NCM faltando, rejeição da SEFAZ, erro do provedor. O motivo verdadeiro
estava em `error_message`, ali do lado, e ninguém o entregava.
"""
import pytest

from apps.invoices.models import Invoice
from apps.invoices.services import fiscal_refusal_message, with_fiscal_state

pytestmark = pytest.mark.django_db


class NotaFalsa:
    """O bastante para `fiscal_state_of` e `with_fiscal_state` decidirem."""

    def __init__(self, status, error_message="", fiscal_payload=None):
        self.status = status
        self.error_message = error_message
        self.fiscal_payload = fiscal_payload or {}
        self.emission_type = ""


def test_recusa_sempre_traz_message():
    nota = NotaFalsa(Invoice.STATUS_ERROR, error_message="Rejeicao 539: duplicidade de NF-e")
    dados = with_fiscal_state({}, nota)

    assert dados["emitted"] is False
    assert dados["message"], "uma recusa sem motivo faz o PDV inventar a causa"


def test_o_texto_da_sefaz_vem_na_frente():
    """Nenhuma frase nossa explica uma rejeição melhor que a própria rejeição."""
    nota = NotaFalsa(Invoice.STATUS_ERROR, error_message="Rejeicao 225: falha no schema XML")
    assert "Rejeicao 225" in with_fiscal_state({}, nota)["message"]


def test_sem_detalhe_o_estado_vira_frase_util():
    nota = NotaFalsa(Invoice.STATUS_ERROR)
    mensagem = with_fiscal_state({}, nota)["message"]

    assert "recusada" in mensagem.lower()
    assert "provedor fiscal não está configurado" not in mensagem, (
        "não inventar causa: o estado é 'rejected', não 'sem provedor'"
    )


def test_configuracao_invalida_diz_isso_e_nao_outra_coisa():
    nota = NotaFalsa(Invoice.STATUS_ERROR, fiscal_payload={"failure": "configuration"})
    mensagem = with_fiscal_state({}, nota)["message"]
    assert "configuração fiscal" in mensagem.lower()


def test_pedido_sem_nota_nao_quebra():
    dados = with_fiscal_state({}, None)
    assert dados["emitted"] is False
    assert dados["message"]


def test_nota_emitida_nao_ganha_message():
    """`message` é o campo da recusa; presente numa nota boa, confunde."""
    nota = NotaFalsa(Invoice.STATUS_ISSUED)
    dados = with_fiscal_state({}, nota)

    assert dados["emitted"] is True
    assert "message" not in dados


def test_a_frase_nunca_volta_vazia():
    """Qualquer estado, inclusive um futuro, produz algo que o operador lê."""
    for status in (Invoice.STATUS_ERROR, Invoice.STATUS_PENDING,
                   Invoice.STATUS_CANCELLED, "estado_inventado"):
        mensagem = fiscal_refusal_message(NotaFalsa(status))
        assert mensagem and mensagem.strip(), f"estado {status} ficou sem frase"
