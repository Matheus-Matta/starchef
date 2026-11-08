"""Recriar a nota: descartar a tentativa que travou e emitir de novo, do zero.

O reenvio transmite a MESMA nota. Isso não serve quando o prazo passou: a
contingência tem 24 h para chegar à SEFAZ, e depois disso o XML assinado (com
o `dhEmi` daquela hora) só volta recusado — o operador clicava em Reenviar e
recebia a mesma recusa. Recriar descarta o XML, a chave e o `cNF` daquela
tentativa e emite a nota normal com a data de agora e o cadastro de agora.

O que NÃO muda:

* a linha da nota: `Invoice` é 1:1 com o pedido, então a nota recriada é a
  mesma linha, e a tentativa descartada fica em
  `fiscal_payload["tentativas_descartadas"]` (número, chave, motivo, XML) para
  a auditoria — viaja com a nota na sincronização;
* o NÚMERO, quando a tentativa já tinha um: nota que nunca foi autorizada não
  gasta o número na SEFAZ (`numero_desta_emissao`), e trocá-lo abriria um
  buraco na série que exigiria inutilização.

Nunca recria o que a SEFAZ pode já ter: nota autorizada se cancela; nota em
processamento ou em conciliação se CONSULTA antes, porque emitir outra daria
duas notas para a mesma venda. A contingência de um tempo esgotado guarda a
chave da tentativa normal (`chave_normal`), e ela também é consultada antes.
"""
from django.db import transaction
from django.utils import timezone

from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import tenant_context
from apps.invoices import contingencia_offline
from apps.invoices.models import Invoice

#: Estados em que a SEFAZ pode já ter a nota: recriar duplicaria a venda.
_CONSULTAR_ANTES = {
    "processing": "A SEFAZ ainda está processando esta nota. Atualize o status antes de recriar.",
    "reconciliation_required": (
        "Não se sabe se a SEFAZ autorizou esta nota (a resposta se perdeu). "
        "Atualize o status antes de recriar: emitir outra daria duas notas para a mesma venda."
    ),
}


class NotaNaoRecriavel(Exception):
    """Conflito de ESTADO (409): a nota não pode ser recriada agora."""


def recriar_nota(invoice, *, user=None):
    from apps.invoices.providers import FiscalProviderError, fiscal_provider_unavailable_reason, get_provider
    from apps.invoices.services import (
        _resolve_fiscal_config, emit_fiscal_invoice, fiscal_state_of, mark_terminal_prints,
    )

    with transaction.atomic():
        nota = Invoice.all_objects.select_for_update().get(pk=invoice.pk)
        with tenant_context(nota.account):
            estado = fiscal_state_of(nota)
            if estado == "authorized":
                raise NotaNaoRecriavel("Nota autorizada não é recriada: cancele-a, se for o caso.")
            if estado == "cancelled":
                raise NotaNaoRecriavel("Nota cancelada não é recriada.")
            if estado in _CONSULTAR_ANTES:
                raise NotaNaoRecriavel(_CONSULTAR_ANTES[estado])
            config = _resolve_fiscal_config(nota.restaurant, nota.branch)
            if config is None:
                raise NotaNaoRecriavel("Configuração fiscal ativa não encontrada para esta nota.")
            indisponivel = fiscal_provider_unavailable_reason(config)
            if indisponivel:
                raise NotaNaoRecriavel(indisponivel)

            try:
                if contingencia_offline.conferir_a_normal(nota, get_provider(config.provider), config):
                    # A tentativa normal FOI autorizada: a nota já existe na
                    # SEFAZ e não há o que recriar.
                    nota.updated_by = user
                    nota.save()
                    return nota
            except FiscalProviderError as exc:
                raise NotaNaoRecriavel(
                    "Não foi possível confirmar com a SEFAZ se a tentativa anterior foi autorizada. "
                    f"Tente de novo em instantes. ({exc})"
                ) from exc

            historico = _historico_com_a_descartada(nota, estado, user)
            _zerar_tentativa(nota)
            nota.updated_by = user
            nota.save()

            nova = emit_fiscal_invoice(nota.order, user=user)
            # A emissão reescreve `fiscal_payload` inteiro; o histórico volta
            # depois. Quem recriou foi alguém no painel: a autorização que
            # chegar depois não dispara cupom automático no balcão.
            nova.fiscal_payload = {**(nova.fiscal_payload or {}), "tentativas_descartadas": historico}
            mark_terminal_prints(nova)
            nova.save(update_fields=["fiscal_payload", "updated_at"])
            record_audit(
                action=AuditLog.ACTION_UPDATED,
                instance=nova,
                actor=user,
                metadata={"fiscal_recreated": True, "discarded_key": historico[-1]["chave"],
                          "status": nova.status},
            )
            return nova


def _historico_com_a_descartada(nota, estado, user):
    payload = nota.fiscal_payload or {}
    descartada = {
        "numero": nota.number,
        "serie": nota.series,
        "chave": nota.access_key,
        "tpEmis": nota.emission_type,
        "situacao": estado,
        "motivo": (nota.error_message or payload.get("contingency_reason") or "")[:500],
        "xml": nota.xml_content,
        "descartada_em": timezone.now().isoformat(),
        "descartada_por": str(user.pk) if user is not None else None,
    }
    return [*payload.get("tentativas_descartadas", []), descartada]


def _zerar_tentativa(nota):
    """Deixa a nota como uma recusa sem rastro: a emissão a reaproveita.

    Sem o `cNF` a emissão sorteia outro, e a chave nova não colide com a da
    tentativa descartada — que pode estar impressa num cupom de contingência.
    """
    nota.status = Invoice.STATUS_ERROR
    nota.emission_type = Invoice.EMISSION_NORMAL
    for campo in ("xml_content", "access_key", "authorization_protocol", "digest_value",
                  "qr_code_data", "error_message"):
        setattr(nota, campo, "")
    nota.authorized_at = None
    nota.fiscal_payload = {}
