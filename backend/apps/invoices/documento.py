"""O documento fiscal NEUTRO: itens com tributos, rateios, totais e pagamentos.

Ele nasceu dentro do provedor Focus, no formato da API dela — e é por isso que
as chaves são as da Focus (`valor_produtos`, `items`, `formas_pagamento`). Saiu
de lá para os provedores dividirem a parte que não depende de quem transmite: a
conferência dos totais, o rateio do desconto sem perder centavo, a situação do
ICMS pelo regime e o código de cada forma de pagamento. A ACBrLib traduz este
mesmo documento para o INI dela (`acbrlib/ini.py`) em vez de remontar tudo.

`rotulo` entra nas mensagens de recusa, para o operador saber qual emissor
recusou.
"""
from decimal import Decimal

from apps.invoices.fiscal import only_digits
from apps.invoices.documento_regras import DocumentoRegras
from apps.invoices.providers_erros import FiscalRejection


class DocumentoFiscal(DocumentoRegras):
    """Monta o item e o documento a partir das regras (`documento_regras`)."""

    def _build_item(self, item, config, *, discount=Decimal("0.00"), other_expenses=Decimal("0.00")):
        payload = {
            "numero_item": item.line_number,
            "codigo_produto": item.code or str(item.line_number),
            "descricao": item.description,
            "codigo_ncm": item.ncm or "00000000",
            "cfop": item.cfop or (config.default_profile and config.default_profile.cfop) or "5102",
            "unidade_comercial": item.unit,
            "quantidade_comercial": str(item.quantity),
            "valor_unitario_comercial": str(item.unit_price),
            "valor_bruto": str(item.total_price),
            "unidade_tributavel": item.unit,
            "quantidade_tributavel": str(item.quantity),
            "valor_unitario_tributavel": str(item.unit_price),
            "icms_origem": item.origem or "0",
            "icms_situacao_tributaria": self._icms_situation(item, config),
            "pis_situacao_tributaria": item.pis_cst or "49",
            "pis_valor": str(item.pis_value),
            "cofins_situacao_tributaria": item.cofins_cst or "49",
            "cofins_valor": str(item.cofins_value),
            "valor_total_tributos": str(item.approx_tax_value),
        }
        if item.cest:
            payload["codigo_cest"] = item.cest
        if discount:
            payload["valor_desconto"] = str(discount)
        if other_expenses:
            payload["valor_outras_despesas"] = str(other_expenses)
        if item.icms_rate:
            payload.update(
                {
                    "icms_base_calculo": str(item.icms_base),
                    "icms_aliquota": str(item.icms_rate),
                    "icms_valor": str(item.icms_value),
                }
            )
        if item.pis_rate:
            payload["pis_base_calculo"] = str(item.total_price)
            payload["pis_aliquota_porcentual"] = str(item.pis_rate)
        if item.cofins_rate:
            payload["cofins_base_calculo"] = str(item.total_price)
            payload["cofins_aliquota_porcentual"] = str(item.cofins_rate)
        return payload

    def _build_payload(self, invoice, config):
        cls = type(self)
        items = list(invoice.items.all().order_by("line_number"))
        if not items:
            raise FiscalRejection(f"{cls.rotulo}: a nota nao possui itens fiscais.")
        other_expenses = self._validate_totals(invoice, items)
        discounts_by_item = self._allocate_discount(items, invoice.discount_total)
        expenses_by_item = self._allocate_total(items, other_expenses)
        payments = self._build_payments(invoice)
        change_total = sum(
            (
                payment.change_amount
                for payment in invoice.order.payments.filter(status="approved", payment_method__method_type="cash")
            ),
            start=0,
        )
        payload = {
            "natureza_operacao": "Venda ao consumidor",
            "data_emissao": invoice.fiscal_payload.get("emission"),
            "indicador_inscricao_estadual_destinatario": "9",
            "local_destino": "1",
            "consumidor_final": "1",
            "finalidade_emissao": "1",
            "presenca_comprador": "4" if invoice.order.order_type == "delivery" else "1",
            # SEM MASCARA. `FiscalConfig.cnpj` tem 18 caracteres justamente
            # para caber "00.000.000/0000-00", e o cadastro aceita os dois
            # formatos. A Focus compoe a CHAVE DE ACESSO a partir deste campo
            # — mandar pontuacao produz uma chave cujo digito verificador nao
            # fecha ("Rejeicao: Digito Verificador da chave de acesso composta
            # invalida"). O cadastro da empresa (`focus.py`) ja normalizava; o
            # payload da nota nao.
            "cnpj_emitente": only_digits(config.cnpj),
            "valor_produtos": str(invoice.products_total),
            "valor_desconto": str(invoice.discount_total),
            "valor_outras_despesas": str(other_expenses),
            "valor_total": str(invoice.total_amount),
            "valor_total_tributos": str(invoice.tax_approx_total),
            "modalidade_frete": "9",
            "items": [
                self._build_item(
                    item,
                    config,
                    discount=discounts_by_item.get(item.pk, Decimal("0.00")),
                    other_expenses=expenses_by_item.get(item.pk, Decimal("0.00")),
                )
                for item in items
            ],
            "formas_pagamento": payments,
        }
        if change_total:
            payload["valor_troco"] = str(change_total)
        if invoice.recipient_cpf:
            payload["cpf_destinatario"] = only_digits(invoice.recipient_cpf)
            payload["nome_destinatario"] = invoice.recipient_name
        elif invoice.recipient_cnpj:
            payload["cnpj_destinatario"] = "".join(
                character
                for character in invoice.recipient_cnpj.upper()
                if character.isalnum()
            )
            payload["nome_destinatario"] = invoice.recipient_name
        return payload
