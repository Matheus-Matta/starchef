"""As regras do documento fiscal que não dependem de quem transmite.

Conferência dos totais, rateio sem perder centavo, situação do ICMS pelo regime
e o código de cada forma de pagamento. Valem para a Focus e para a ACBrLib —
ver `documento.py`. `rotulo` é o nome do emissor nas mensagens de recusa.
"""
from decimal import ROUND_HALF_UP, Decimal

from apps.invoices.discount_allocation import ratear_desconto
from apps.invoices.models import FiscalConfig
from apps.invoices.providers_erros import FiscalRejection

TWO_PLACES = Decimal("0.01")

#: Formas com o grupo do cartão na nota: crédito, débito e PIX.
COM_GRUPO_DO_CARTAO = {"03", "04", "17"}
#: Pagamento NÃO integrado: a maquininha é separada do sistema, então não há
#: CNPJ da credenciadora, bandeira nem autorização a informar — e o
#: `tpIntegra=2` é o que dispensa os três. Sem o grupo, a SEFAZ recusava a
#: NFC-e paga no cartão com 391 ("Não informados os dados do cartão").
NAO_INTEGRADO = "2"
#: "Outros": o único tPag que leva a descrição (xPag).
OUTROS = "99"


class DocumentoRegras:
    rotulo = "Focus NFe"

    @staticmethod
    def _payment_code(payment):
        method = payment.payment_method
        if method.method_type == "cash":
            return "01"
        if method.method_type == "pix":
            return "17"
        if method.method_type == "voucher":
            return "10"
        if method.method_type == "card":
            if payment.card_subtype == "debit":
                return "04"
            if payment.card_subtype == "credit":
                return "03"
        return "99"

    @classmethod
    def _forma_de_pagamento(cls, payment, valor):
        forma = {"forma_pagamento": cls._payment_code(payment), "valor_pagamento": valor}
        if forma["forma_pagamento"] in COM_GRUPO_DO_CARTAO:
            forma["tipo_integracao"] = NAO_INTEGRADO
        if forma["forma_pagamento"] == OUTROS:
            # tPag=99 sem descrição é a 441; descrição em outro tPag, a 442.
            forma["descricao_pagamento"] = (payment.payment_method.name or "Outros")[:60]
        return forma

    def _build_payments(self, invoice):
        from apps.invoices.pedido_completo import motivo_sem_pagamento
        from apps.payments.models import Payment

        # NFC-e não aceita tPag=90 (899) nem pagamento abaixo do total (865):
        # recusar aqui diz o que falta, em vez de gastar a ida à SEFAZ.
        if str(invoice.document_model) == FiscalConfig.MODEL_NFCE:
            motivo = motivo_sem_pagamento(invoice.order, invoice.total_amount)
            if motivo:
                raise FiscalRejection(f"{type(self).rotulo}: {motivo}")

        payments = invoice.order.payments.filter(status=Payment.STATUS_APPROVED).select_related("payment_method")
        result = []
        for payment in payments:
            paid_value = payment.amount
            if payment.payment_method.method_type == "cash":
                paid_value += payment.change_amount
            result.append(self._forma_de_pagamento(payment, str(paid_value)))
        return result or [{"forma_pagamento": "90", "valor_pagamento": "0.00"}]

    @staticmethod
    def _troco(payments, total):
        """vTroco = o que foi ENTREGUE (soma dos vPag) menos o total da nota.

        A SEFAZ confere a conta, e não de onde veio o troco: pagamentos acima
        do total sem vTroco é a rejeição 866. O troco era lido só do
        `change_amount` do dinheiro, e ficava zero no cartão/PIX pago a mais ou
        no desconto dado depois de pagar. Pagamento abaixo do total não vira
        troco negativo — é outra recusa, e correta.
        """
        entregue = sum((Decimal(p["valor_pagamento"]) for p in payments), start=Decimal("0.00"))
        troco = (entregue - Decimal(total)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        return troco if troco > 0 else Decimal("0.00")

    # O desconto tem teto por item (ver `discount_allocation.py`): o rateio
    # comum jogava a sobra no último item, e a SEFAZ rejeita vDesc > vProd.
    _allocate_discount = staticmethod(ratear_desconto)

    @classmethod
    def _allocate_total(cls, items, total):
        """Rateia um total fiscal entre os itens sem perder centavos."""

        total = Decimal(total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if not total:
            return {}

        products_total = sum((item.total_price for item in items), start=Decimal("0.00"))
        if products_total <= 0:
            raise FiscalRejection(f"{cls.rotulo}: nao e possivel ratear valores em uma nota sem produtos.")

        allocations = {}
        allocated = Decimal("0.00")
        for item in items[:-1]:
            amount = (total * item.total_price / products_total).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            amount = min(amount, total - allocated)
            allocations[item.pk] = amount
            allocated += amount
        allocations[items[-1].pk] = total - allocated
        return allocations

    @classmethod
    def _validate_totals(cls, invoice, items):
        """Valida e devolve despesas que explicam o total da NF-e."""

        items_total = sum((item.total_price for item in items), start=Decimal("0.00")).quantize(
            TWO_PLACES, rounding=ROUND_HALF_UP
        )
        products_total = invoice.products_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        discount_total = invoice.discount_total.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        invoice_total = invoice.total_amount.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        if items_total != products_total:
            raise FiscalRejection(
                f"{cls.rotulo}: total dos itens difere do valor dos produtos "
                f"({items_total} != {products_total})."
            )
        if discount_total < 0 or discount_total > products_total:
            raise FiscalRejection(f"{cls.rotulo}: o desconto fiscal deve estar entre zero e o valor dos produtos.")

        other_expenses = invoice_total - products_total + discount_total
        if other_expenses < 0:
            raise FiscalRejection(
                f"{cls.rotulo}: total fiscal inconsistente; o valor total deve corresponder a "
                "produtos - desconto + outras despesas."
            )
        return other_expenses

    @classmethod
    def _icms_situation(cls, item, config):
        """Situacao tributaria do ICMS, escolhida pelo REGIME da empresa.

        Antes era `item.csosn or item.cst_icms or "102"`, sem olhar o CRT. Numa
        empresa de regime normal isso mandava um CSOSN — que so existe no
        Simples — e a SEFAZ recusava de qualquer jeito: o fallback nao evitava
        problema nenhum, so trocava "cadastro incompleto" por "rejeicao".

        Por isso o regime normal sem CST falha aqui mesmo com
        `strict_fiscal_profile` desligado: nao existe valor padrao seguro, e
        adivinhar um CST produziria um documento aceito e errado — pior que a
        recusa. No Simples, CSOSN 102 (tributada sem permissao de credito)
        continua valendo como padrao do varejo.
        """
        if str(config.crt) in {FiscalConfig.CRT_SIMPLES, FiscalConfig.CRT_SIMPLES_EXCESSO}:
            return item.csosn or "102"
        if item.cst_icms:
            return item.cst_icms
        raise FiscalRejection(
            f'{cls.rotulo}: o item "{item.description}" esta sem CST do ICMS e a empresa '
            "esta em regime normal (CRT 3). Informe o CST no perfil fiscal do produto — "
            "CSOSN so vale para o Simples Nacional."
        )
