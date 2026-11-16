"""Ninguém mexe na nota enquanto a transmissão dela está em curso.

Reprocessar, consultar, reenviar ou cancelar no meio da transmissão leria
"não existe" na SEFAZ e mandaria transmitir de novo — ou descartaria a nota
enquanto ela é autorizada. A marca `EM_VOO` (ver `emissao_em_voo.py`) protege
até `EM_VOO_PRAZO`; passado o prazo, o processo morreu e a consulta resolve.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.invoices.models import Invoice
from apps.invoices.services import EM_VOO, emit_fiscal_invoice, reprocess_pending_fiscal_invoices
from apps.invoices.tests.test_sefaz_fora_da_transacao import _limpa, _Observado, pedido  # noqa: F401 — fixtures

pytestmark = pytest.mark.django_db


def test_reprocessamento_nao_mexe_na_nota_em_transmissao(pedido, manager_user):  # noqa: F811 — fixture importada
    """Consultar no meio leria "não existe" e mandaria transmitir de novo."""
    nota = emit_fiscal_invoice(pedido, user=manager_user)
    payload = {**(nota.fiscal_payload or {}), "awaiting": "authorization",
               EM_VOO: timezone.now().isoformat()}
    Invoice.all_objects.filter(pk=nota.pk).update(status=Invoice.STATUS_PENDING, fiscal_payload=payload)

    reprocess_pending_fiscal_invoices()
    assert _Observado.consultas == 0

    # Passado o prazo (o processo morreu no meio), a consulta resolve.
    payload[EM_VOO] = (timezone.now() - timedelta(minutes=10)).isoformat()
    Invoice.all_objects.filter(pk=nota.pk).update(fiscal_payload=payload)
    reprocess_pending_fiscal_invoices()
    assert _Observado.consultas == 1


def _em_voo(nota):
    payload = {**(nota.fiscal_payload or {}), "awaiting": "authorization",
               EM_VOO: timezone.now().isoformat()}
    Invoice.all_objects.filter(pk=nota.pk).update(status=Invoice.STATUS_PENDING, fiscal_payload=payload)
    nota.refresh_from_db()
    return nota


def test_consultar_reenviar_ou_cancelar_no_meio_da_transmissao_nao_mexe_na_nota(pedido, manager_user):  # noqa: F811 — fixture importada
    """O PDV consulta em laço logo depois da venda; o operador pode cancelar.

    Consultar no meio leria "não existe" e mandaria retransmitir; cancelar
    descartaria a nota como "nunca autorizada" enquanto a SEFAZ a autoriza.
    """
    from django.core.exceptions import ValidationError

    from apps.invoices.services import (
        cancel_fiscal_invoice,
        refresh_fiscal_invoice_status,
        resend_fiscal_invoice,
    )

    nota = _em_voo(emit_fiscal_invoice(pedido, user=manager_user))

    devolvida = refresh_fiscal_invoice_status(nota, user=manager_user, manual_print=True)
    assert _Observado.consultas == 0
    assert devolvida.status == Invoice.STATUS_PENDING
    with pytest.raises(ValidationError):
        resend_fiscal_invoice(nota, user=manager_user)
    with pytest.raises(ValidationError):
        cancel_fiscal_invoice(nota, reason="cliente desistiu", user=manager_user)
    nota.refresh_from_db()
    assert nota.status == Invoice.STATUS_PENDING
