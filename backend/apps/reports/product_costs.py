"""Custo × venda por produto, no período.

O custo vem da BAIXA DE ESTOQUE da venda: ela grava o custo de cada insumo
na época (negativo, como todo o livro) ligado ao item vendido, e o estorno
devolve com o sinal contrário — a soma já é o custo líquido. Usar o custo de
HOJE reescreveria a margem do mês passado a cada compra nova.

Produto sem baixa (sem ficha técnica nem vínculo de estoque) não tem custo
gravado: usa o do cadastro (custo médio de compra, ou o estimado da ficha), e
a linha diz `cost_source = "cadastro"` para ninguém ler isso como histórico.

Só pedido pago; item cancelado e cortesia ficam de fora.
"""
import csv
from collections import defaultdict
from decimal import Decimal

from django.db.models import Q, Sum
from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order, OrderItem
from apps.reports.cash_movements import _between, _period
from apps.reports.views import TenantReportMixin
from apps.stock.models import StockMovement

ZERO = Decimal("0.00")
CENTAVOS = Decimal("0.01")


def _custo_do_cadastro(produto):
    return produto.current_average_cost or produto.estimated_cost or ZERO


class ProductCostsReportView(TenantReportMixin, APIView):
    def get(self, request):
        try:
            inicio, fim = _period(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        escopo = {f"order__{k}": v for k, v in self.tenant_filter().items()}
        itens = (
            self.tenant_manager(OrderItem)
            .filter(Q(order__payment_status=Order.PAYMENT_PAID) | Q(order__status=Order.STATUS_PAID), **escopo,
                    **_between("order__opened_at", inicio, fim))
            .exclude(status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
        )
        baixas = dict(
            self.tenant_manager(StockMovement)
            .filter(order_item__in=itens)
            .values_list("order_item_id")
            .annotate(custo=Sum("total_cost"))
        )
        linhas = defaultdict(lambda: {"quantity": Decimal("0"), "revenue": ZERO, "cost": ZERO, "fontes": set()})
        for item in itens.select_related("product"):
            linha = linhas[item.product_id]
            linha["produto"] = item.product
            linha["quantity"] += item.quantity
            linha["revenue"] += item.total_price
            if item.id in baixas:
                linha["cost"] += -baixas[item.id]
                linha["fontes"].add("baixa")
            else:
                custo = (_custo_do_cadastro(item.product) * item.quantity).quantize(CENTAVOS)
                linha["cost"] += custo
                linha["fontes"].add("cadastro")
        resultado = [self._linha(dados) for dados in linhas.values()]
        resultado.sort(key=lambda linha: linha["margin"], reverse=True)
        totais = {campo: sum((linha[campo] for linha in resultado), ZERO) for campo in ("revenue", "cost", "margin")}
        if request.query_params.get("export") == "csv":
            return self._csv(resultado)
        return Response({"by_product": resultado, "totals": totais})

    @staticmethod
    def _linha(dados):
        produto, receita, custo = dados["produto"], dados["revenue"], dados["cost"].quantize(CENTAVOS)
        margem = receita - custo
        fontes = dados["fontes"]
        return {
            "product_id": str(produto.id),
            "product_name": produto.name,
            "code": produto.internal_code or "",
            "quantity": dados["quantity"],
            "revenue": receita,
            "cost": custo,
            "margin": margem,
            "margin_percent": (margem / receita * 100).quantize(CENTAVOS) if receita else ZERO,
            "cost_source": fontes.pop() if len(fontes) == 1 else "misto",
        }

    @staticmethod
    def _csv(linhas):
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = 'attachment; filename="custo_por_produto.csv"'
        escritor = csv.writer(resposta)
        escritor.writerow(["Código", "Produto", "Quantidade", "Vendido", "Custo", "Margem", "Margem %", "Origem do custo"])
        for linha in linhas:
            escritor.writerow([
                linha["code"], linha["product_name"], linha["quantity"].quantize(Decimal("0.001")),
                linha["revenue"], linha["cost"], linha["margin"], linha["margin_percent"], linha["cost_source"],
            ])
        return resposta
