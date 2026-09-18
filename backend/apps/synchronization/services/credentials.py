"""Canal próprio para o segredo de emissão. Emprestado, nunca replicado.

A decisão que este módulo executa está em `decisions.py` desde o começo —
"Credencial de emissor: canal próprio, cifrado" — e nunca tinha sido
construída. Enquanto isso, o certificado A1 da empresa viajava dentro do
payload de sincronização.

**Por que o payload não serve, mesmo cifrado.** O tráfego é AES-256-GCM sobre
WSS, e isso está correto. Mas o evento é gravado em `SyncEvent.payload`, um
JSONField em TEXTO PURO, nos dois bancos. A cifra protege o cabo, não o disco.
Um segredo ali fica legível na tabela de eventos da nuvem, na de cada loja — em
computadores dentro das lojas —, em todo backup dos dois, e para sempre, porque
evento não é apagado: é o que garante a recuperação depois de uma semana sem
internet.

**O que este canal faz diferente.** A loja PEDE a credencial quando precisa
emitir, autenticada pelo mesmo token do nó. A resposta é um envelope AES-GCM
que a loja abre em memória, usa e descarta. Nada entra na tabela de eventos,
nada sobra em backup, e a nuvem registra quem pediu, quando e de onde.

A diferença prática é a revogação: um segredo replicado está no disco da loja
para sempre e revogar não o apaga de lá. Um segredo emprestado morre junto com
o token do nó.
"""
import logging

from apps.synchronization.constants import NodeType
from apps.synchronization.services import crypto, guard, provisioning

logger = logging.getLogger(__name__)


class CredentialsUnavailable(Exception):
    """Não há o que entregar, e o motivo vem junto."""


def _config_do_no(no):
    """A configuração fiscal que vale para a loja deste nó.

    Usa o `restaurant` do nó quando ele existe; senão, a configuração ativa da
    conta. Nunca atravessa conta — seria entregar o certificado de um cliente
    ao servidor de outro.
    """
    from apps.invoices.models import FiscalConfig

    consulta = FiscalConfig.all_objects.filter(account_id=no.account_id, is_active=True)
    if no.restaurant_id:
        especifica = consulta.filter(branch__restaurant_id=no.restaurant_id).first()
        if especifica is not None:
            return especifica
    return consulta.first()


def montar_pacote(no):
    """Os segredos de emissão que ESTE nó pode receber. Nada além.

    Só nó LOCAL recebe: a nuvem não pede credencial a ninguém, e um nó de nuvem
    pedindo seria sinal de token vazado sendo usado no lugar errado.
    """
    guard.ensure_environment()

    if no.node_type != NodeType.LOCAL:
        raise CredentialsUnavailable(
            "Apenas o nó de uma loja recebe credencial de emissão."
        )

    config = _config_do_no(no)
    if config is None:
        raise CredentialsUnavailable(
            "Nenhuma configuração fiscal ativa para a loja deste nó."
        )

    pacote = {
        "fiscal_config_id": str(config.id),
        "environment": config.environment,
        "provider": config.provider,
        # O CSC monta o QR Code da NFC-e no terminal.
        "csc_id": config.csc_id or "",
        "csc_token": config.csc_token or "",
        # O certificado A1 e sua senha, para a assinatura local quando o
        # Comunicador estiver em uso.
        "certificate_base64": config.focus_certificate_base64 or "",
        "certificate_password": config.focus_certificate_password or "",
    }
    disponiveis = sorted(chave for chave, valor in pacote.items() if valor)
    logger.info(
        "sync-credenciais: pacote montado para o nó %s (conta %s) — campos com "
        "valor: %s", no.id, no.account_id, ", ".join(disponiveis),
    )
    return pacote


def cifrar_para(no, pacote):
    """Envelope AES-GCM com a chave do ambiente, amarrado ao nó de destino.

    O id do nó vai como dado associado do GCM: o envelope não é apenas
    ilegível para quem não tem a chave, ele é INVÁLIDO se for reapresentado
    como se fosse de outro nó. Sem isso, um envelope capturado serviria em
    qualquer loja do mesmo ambiente.
    """
    chave = provisioning.chave_do_ambiente()
    if not chave:
        raise CredentialsUnavailable(
            "SYNC_ENCRYPTION_KEY não configurada: sem ela o segredo viajaria em claro."
        )
    nonce, ciphertext = crypto.encrypt(pacote, chave, associated_data=str(no.id).encode())
    return {
        "nonce": nonce,
        "ciphertext": ciphertext,
        "checksum": crypto.checksum(pacote),
        "key_id": no.encryption_key_id or "",
    }


def abrir(envelope, no_id):
    """Lado LOJA: abre o envelope e confere o checksum antes de usar."""
    chave = provisioning.chave_do_ambiente()
    if not chave:
        raise CredentialsUnavailable("SYNC_ENCRYPTION_KEY não configurada nesta loja.")

    pacote = crypto.decrypt(
        envelope["nonce"], envelope["ciphertext"], chave,
        associated_data=str(no_id).encode(),
    )
    esperado = envelope.get("checksum")
    if esperado and crypto.checksum(pacote) != esperado:
        raise CredentialsUnavailable(
            "Checksum do pacote de credenciais não confere — não use este conteúdo."
        )
    return pacote
