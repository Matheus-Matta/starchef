"""Relatório por cupom: quantas vezes foi usado, quanto descontou, quanto vendeu.

Cada linha é um cupom. `net` é o que os pedidos cobraram (já com o desconto);
`gross` é o que teriam cobrado sem ele — a soma dos dois valores JÁ
arredondados de cada pedido, nunca um percentual recalculado sobre o total.

Só pedido PAGO entra. O cancelamento devolve o resgate (o cupom volta a valer
para o cliente), e um resgate antigo que tenha ficado num pedido cancelado
mostraria desconto de uma venda que não existiu.
"""
import csv
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.orders.models import Order
from apps.promotions.models import CouponRedemption
from apps.reports.cash_movements import _between, _period
from apps.reports.views import TenantReportMixin

ZERO = Decimal("0.00")
_PAGO = Q(order__payment_status=Order.PAYMENT_PAID) | Q(order__status=Order.STATUS_PAID)


def mascarar_documento(documento):
    """CPF no relatório só com o miolo: identifica sem expor."""
    digitos = "".join(c for c in str(documento or "") if c.isdigit())
    if len(digitos) != 11:
        return "***" if digitos else ""
    return f"***.{digitos[3:6]}.{digitos[6:9]}-**"


class CouponsReportView(TenantReportMixin, APIView):
    def get(self, request):
        try:
            inicio, fim = _period(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        escopo = {f"order__{campo}": valor for campo, valor in self.tenant_filter().items()}
        resgates = (
            self.tenant_manager(CouponRedemption)
            .filter(_PAGO, **escopo, **_between("order__opened_at", inicio, fim))
        )
        cupom = request.query_params.get("coupon")
        if cupom:
            return Response({"redemptions": self._usos(resgates.filter(coupon_id=cupom))})

        linhas = self._por_cupom(resgates)
        totais = {
            "uses": sum(linha["uses"] for linha in linhas),
            "discount": sum((linha["discount"] for linha in linhas), ZERO),
            "net": sum((linha["net"] for linha in linhas), ZERO),
            "gross": sum((linha["gross"] for linha in linhas), ZERO),
        }
        if request.query_params.get("export") == "csv":
            return self._csv(linhas, totais, request)
        return Response({"by_coupon": linhas, "totals": totais})

    @staticmethod
    def _por_cupom(resgates):
        agrupado = (
            resgates.values("coupon_id", "coupon__code", "coupon__name")
            .annotate(
                uses=Count("id"),
                discount=Sum("amount"),
                net=Sum("order__total"),
            )
            .order_by("-discount", "coupon__code")
        )
        linhas = []
        for linha in agrupado:
            desconto = linha["discount"] or ZERO
            liquido = linha["net"] or ZERO
            linhas.append({
                "coupon_id": str(linha["coupon_id"]),
                "code": linha["coupon__code"],
                "name": linha["coupon__name"],
                "uses": linha["uses"],
                "discount": desconto,
                "net": liquido,
                "gross": liquido + desconto,
            })
        return linhas

    @staticmethod
    def _usos(resgates):
        return [
            {
                "date": timezone.localtime(r.order.opened_at).isoformat(),
                "order_id": str(r.order_id),
                "order_sequence": r.order.sequence,
                "document": mascarar_documento(r.document),
                "net": r.order.total,
                "discount": r.amount,
            }
            for r in resgates.select_related("order").order_by("-order__opened_at", "-order__sequence")
        ]

    @staticmethod
    def _csv(linhas, totais, request):
        de = request.query_params.get("date_from") or "inicio"
        ate = request.query_params.get("date_to") or "hoje"
        resposta = HttpResponse(content_type="text/csv; charset=utf-8")
        resposta["Content-Disposition"] = f'attachment; filename="cupons_{de}_{ate}.csv"'
        escritor = csv.writer(resposta)
        escritor.writerow(["Cupom", "Nome", "Usos", "Total vendido", "Total descontado", "Total liquido"])
        for linha in linhas:
            escritor.writerow([
                linha["code"], linha["name"], linha["uses"],
                linha["gross"], linha["discount"], linha["net"],
            ])
        escritor.writerow([
            "TOTAL", "", totais["uses"], totais["gross"], totais["discount"], totais["net"],
        ])
        return resposta
