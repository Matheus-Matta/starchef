"""A sincronização diz no log o que enviou, recebeu e por que falhou.

O log só dizia "15 evento(s) voltaram para a fila", a cada volta, sem dizer
quais nem o motivo: o erro ficava gravado no banco, longe de quem olhava.
"""
import logging
from types import SimpleNamespace

from apps.synchronization.constants import EventStatus
from apps.synchronization.services import registro, retry


def _evento(tipo="payment", **extra):
    base = {"event_id": "e1", "entity_type": tipo, "entity_id": "p1", "attempts": 0,
            "last_error": "", "status": EventStatus.PENDING, "next_attempt_at": None}
    return SimpleNamespace(**{**base, **extra})


def _linhas(caplog):
    return [r.getMessage() for r in caplog.records if r.name == "starchef.sync"]


def test_a_falha_aparece_com_o_tipo_a_tentativa_e_o_erro(caplog):
    caplog.set_level(logging.INFO, logger="starchef.sync")

    retry.mark_failure(_evento(), "Payment.order aponta para Order 9, que ainda não existe aqui.",
                       save=False)

    (linha,) = _linhas(caplog)
    assert linha.startswith("sync: FALHOU payment/p1 (tentativa 1 de 12")
    assert "Order 9, que ainda não existe aqui" in linha
    assert caplog.records[-1].levelno == logging.WARNING


def test_quando_desiste_o_log_e_erro(caplog):
    caplog.set_level(logging.INFO, logger="starchef.sync")

    retry.mark_failure(_evento(attempts=retry.MAX_TENTATIVAS - 1), "recusado", save=False)

    assert _linhas(caplog) == ["sync: DESISTIU de payment/p1 após 12 tentativa(s) — recusado"]
    assert caplog.records[-1].levelno == logging.ERROR


def test_envio_e_recebimento_resumem_os_tipos(caplog):
    caplog.set_level(logging.INFO, logger="starchef.sync")
    loja = SimpleNamespace(id="n1", name="Loja Centro")
    lote = [_evento("order"), _evento("order"), _evento("payment")]

    registro.enviado(lote, loja)
    registro.recebido(lote, [{"event_id": "x", "error": "fora do escopo"}], loja)

    assert _linhas(caplog) == [
        "sync: ENVIADOS 3 evento(s) para Loja Centro — order×2, payment×1",
        "sync: RECEBIDOS 3 evento(s) de Loja Centro — order×2, payment×1 | 1 RECUSADO(S)",
    ]


def test_lote_vazio_nao_enche_o_log(caplog):
    caplog.set_level(logging.INFO, logger="starchef.sync")

    registro.enviado([])
    registro.recebido([], [], None)
    registro.confirmado(None, [], [], [])
    registro.aplicados([])

    assert _linhas(caplog) == []
