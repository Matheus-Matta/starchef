"""O fornecedor da nota de entrada, achado ou cadastrado na importação.

Procura pelo CNPJ/CPF do emitente — só dígitos, porque o cadastro manual
costuma ter a máscara ("08.969.770/0001-59"). Não existindo, cria com o que a
nota traz. Existindo, só preenche campos vazios: o que alguém digitou no
cadastro vale mais que a nota.
"""
import logging
import re

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)

_CAMPOS_DO_ENDERECO = ("street", "number", "district", "city", "state", "zip_code", "phone")


def _digitos(valor):
    return re.sub(r"\D", "", valor or "")


def _achar(account, documento):
    from apps.stock.models import Supplier

    candidatos = Supplier.all_objects.filter(account=account, deleted_at__isnull=True).exclude(tax_id="")
    # O índice não ajuda com máscara; o filtro por sufixo corta a varredura.
    for fornecedor in candidatos.filter(tax_id__endswith=documento[-2:]):
        if _digitos(fornecedor.tax_id) == documento:
            return fornecedor
    return None


def ensure_supplier_from_nfe(parsed, *, account, restaurant=None):
    """Devolve o fornecedor do emitente. Nunca derruba a importação."""
    from apps.stock.models import Supplier

    documento = _digitos(parsed.supplier_cnpj or getattr(parsed, "supplier_cpf", ""))
    if not documento:
        return None
    dados = {
        "legal_name": (parsed.supplier_name or "")[:180],
        "state_registration": (getattr(parsed, "supplier_ie", "") or "")[:20],
        **{
            campo: (valor or "")[: Supplier._meta.get_field(campo).max_length]
            for campo, valor in (getattr(parsed, "supplier_address", None) or {}).items()
            if campo in _CAMPOS_DO_ENDERECO
        },
    }
    try:
        existente = _achar(account, documento)
        if existente is not None:
            faltando = [campo for campo, valor in dados.items() if valor and not getattr(existente, campo)]
            for campo in faltando:
                setattr(existente, campo, dados[campo])
            if faltando:
                existente.save(update_fields=[*faltando, "updated_at"])
            return existente
        nome = (getattr(parsed, "supplier_trade_name", "") or parsed.supplier_name or documento)[:160]
        for tentativa in (nome, f"{nome[:140]} ({documento})"):
            try:
                with transaction.atomic():
                    return Supplier.all_objects.create(
                        account=account, restaurant=restaurant, name=tentativa, tax_id=documento, **dados,
                    )
            except IntegrityError:
                continue  # nome único na conta: o segundo leva o documento
    except Exception:  # noqa: BLE001 — cadastro de apoio não pode travar a nota
        logger.exception("Fornecedor da nota %s não pôde ser cadastrado", parsed.access_key)
    return None
