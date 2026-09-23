"""Lado NUVEM: entrega ao provedor fiscal o documento que a loja montou.

A divisão é essa: a loja MONTA — ela tem o pedido, os itens e os impostos — e
a nuvem TRANSMITE, com a credencial dela. A resposta volta crua, porque quem
sabe interpretá-la é a loja: é lá que `apply_response` grava número, série,
chave e protocolo na nota, e é de lá que o cupom sai.

Traduzir a resposta aqui criaria um segundo dialeto para manter, e a nuvem —
que só transmite em nome da loja — não tem o que dizer sobre o documento.
"""
import logging

from apps.synchronization.constants import NodeType
from apps.synchronization.services import guard

logger = logging.getLogger(__name__)


class RelayRecusado(Exception):
    """Não dá para transmitir por este nó, e o motivo vem junto."""


def config_do_no(no):
    """A configuração fiscal da loja deste nó. Nunca atravessa conta."""
    from apps.synchronization.services.credentials import _config_do_no

    return _config_do_no(no)


def executar(no, *, operacao, reference, document_model, payload=None, reason=""):
    """Faz a chamada ao provedor e devolve `(status_code, dados)`."""
    guard.ensure_environment()

    if no.node_type != NodeType.LOCAL:
        raise RelayRecusado("Apenas o nó de uma loja transmite por este canal.")

    config = config_do_no(no)
    if config is None:
        raise RelayRecusado("Nenhuma configuração fiscal ativa para a loja deste nó.")

    from apps.invoices.providers import get_provider

    provedor = get_provider(config.provider)
    executor = getattr(provedor, "relay_execute", None)
    if executor is None:
        raise RelayRecusado(
            f"O provedor '{config.provider}' não transmite por conta da loja."
        )
    if operacao not in {provedor.TRANSMITIR, provedor.CONSULTAR, provedor.CANCELAR}:
        raise RelayRecusado(f"Operação desconhecida: {operacao!r}.")

    logger.info(
        "sync-fiscal: %s para o nó %s (conta %s) ref=%s",
        operacao, no.id, no.account_id, reference,
    )
    return executor(
        config,
        operacao=operacao,
        reference=reference,
        document_model=document_model,
        payload=payload,
        reason=reason,
    )
