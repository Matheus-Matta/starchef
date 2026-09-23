"""Lado LOJA: pede à nuvem que transmita a nota ao provedor.

A loja MONTA o documento — ela tem o pedido, os itens e os impostos — e a
nuvem o TRANSMITE, com a credencial dela. A resposta do provedor volta crua e
a loja a interpreta como se tivesse feito a chamada: `apply_response` grava
número, série, chave, protocolo e QR Code, e o PDV imprime.

Duas coisas melhoram com isso:

* o segredo de emissão deixa de precisar chegar ao computador dentro do
  restaurante no caminho normal;
* o contador da Focus passa a ter **um dono só** — era a divergência entre
  lojas que produzia "Duplicidade de NF-e, com diferença na Chave de Acesso".

**Falha aqui é INDISPONIBILIDADE, e é o ponto mais delicado do arquivo.** Não
conseguir falar com a nuvem não diz nada sobre a validade do documento: a nota
fica pendente e volta na retransmissão. Se isto virasse rejeição, a nota seria
marcada como recusada definitivamente por causa de um cabo de rede — e uma
recusa não é retentada nunca mais.
"""
import logging

from django.conf import settings

from apps.invoices.providers import FiscalConfigurationError, FiscalUnavailable

logger = logging.getLogger(__name__)

#: Quanto esperar a nuvem. Maior que o do provedor de propósito: há um salto a
#: mais no caminho, e um timeout curto aqui transformaria uma emissão que deu
#: certo em "não sei o que aconteceu" — o estado mais caro de todos.
TIMEOUT_PADRAO = 45


def deve_delegar(config):
    """Esta instalação delega a transmissão à nuvem?

    Só a LOJA delega, e só quando sabe para onde. A nuvem nunca delega: ela é
    o destino. Uma instalação única (sem sincronização) também não — não há
    a quem pedir, e o segredo está nela mesma.
    """
    if not getattr(settings, "FISCAL_TRANSMIT_VIA_CLOUD", True):
        return False
    if str(getattr(settings, "SYNC_NODE_TYPE", "") or "").strip().upper() != "LOCAL":
        return False
    return bool((getattr(settings, "SYNC_CLOUD_API_URL", "") or "").strip())


def executar(config, *, operacao, reference, document_model, payload=None, reason=""):
    """Pede a operação à nuvem. Devolve `(status_code, dados)` do provedor."""
    import requests

    base = (getattr(settings, "SYNC_CLOUD_API_URL", "") or "").rstrip("/")
    token = getattr(settings, "SYNC_AUTH_TOKEN", "") or ""
    if not token:
        # Sem identidade não há pedido possível, e isso não se resolve
        # tentando de novo: é configuração.
        raise FiscalConfigurationError(
            "Transmissão pela nuvem: SYNC_AUTH_TOKEN não configurado nesta loja."
        )

    corpo = {
        "operation": operacao,
        "reference": reference,
        "document_model": document_model,
        "reason": reason,
    }
    if payload is not None:
        corpo["payload"] = payload

    try:
        resposta = requests.post(
            f"{base}/api/v1/sync/fiscal/",
            json=corpo,
            headers={"Authorization": f"Bearer {token}"},
            timeout=int(getattr(settings, "FISCAL_RELAY_TIMEOUT", TIMEOUT_PADRAO)),
        )
    except requests.RequestException as erro:
        raise FiscalUnavailable(
            f"Transmissão pela nuvem: não foi possível falar com a nuvem ({erro})."
        ) from erro

    if resposta.status_code == 403:
        raise FiscalConfigurationError(
            "Transmissão pela nuvem: a nuvem recusou a identidade desta loja."
        )
    if resposta.status_code >= 500 or resposta.status_code == 429:
        raise FiscalUnavailable(
            f"Transmissão pela nuvem: a nuvem respondeu HTTP {resposta.status_code}."
        )

    dados = resposta.json() if resposta.content else {}
    if resposta.status_code >= 400:
        # 409 é a nuvem dizendo que NÃO transmitiu (sem configuração fiscal,
        # nó errado). Nunca chegou ao provedor — logo, indisponibilidade.
        raise FiscalUnavailable(
            f"Transmissão pela nuvem recusada: {dados.get('detail') or resposta.status_code}"
        )

    logger.info(
        "fiscal-relé: %s devolvida pela nuvem (provedor HTTP %s) ref=%s",
        operacao, dados.get("status_code"), reference,
    )
    return int(dados.get("status_code") or 0), dados.get("data") or {}
