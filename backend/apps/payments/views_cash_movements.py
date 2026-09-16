"""Historico de movimentacoes do caixa entre sessoes.

A sessao (`/cash-register/<id>/`) ja lista os movimentos dela. O que faltava
era olhar o caixa ao longo do tempo — todas as sangrias da semana, tudo que um
operador lancou, os suprimentos de um caixa fisico — e levar isso para uma
planilha. So leitura: quem cria movimento e a sessao, com as regras dela.
"""

import csv

import django_filters
from django.http import HttpResponse

from apps.core.viewsets import ReadOnlyTenantViewSet
from apps.payments.models import CashMovement
from apps.payments.serializers import CashMovementSerializer


class CashMovementFilterSet(django_filters.FilterSet):
    # Intervalo por data do lancamento, inclusivo nas duas pontas.
    date_from = django_filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_to = django_filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    cash_station = django_filters.UUIDFilter(field_name="cash_register__cash_station_id")

    class Meta:
        model = CashMovement
        fields = ["cash_register", "cash_station", "operator", "movement_type", "status", "date_from", "date_to"]


MOVEMENT_LABELS = {
    "opening": "Abertura",
    "sale": "Venda em dinheiro",
    "withdrawal": "Sangria",
    "supply": "Suprimento",
    "closing": "Fechamento",
    "adjustment": "Ajuste",
    "refund": "Estorno",
}

AUTHORIZATION_LABELS = {
    "pending": "Pendente",
    "cash_password": "Senha do caixa",
    "manager": "Gerente",
    "automatic": "Automatica",
}


class CashMovementViewSet(ReadOnlyTenantViewSet):
    # O caixa e operacao base (como `/cash-register/`), nao do modulo financeiro.
    serializer_class = CashMovementSerializer
    queryset = (
        CashMovement.objects.select_related(
            "cash_register__cash_station",
            "cash_register__opened_terminal",
            "operator",
            "authorized_by",
            "payment__order",
            "payment__payment_method",
        )
        .order_by("-created_at")
    )
    filterset_class = CashMovementFilterSet
    ordering_fields = ["created_at", "amount"]

    def list(self, request, *args, **kwargs):
        if request.query_params.get("export") == "csv":
            queryset = self.filter_queryset(self.get_queryset())
            return self._csv(queryset[:5000])
        return super().list(request, *args, **kwargs)

    @staticmethod
    def _csv(queryset):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="movimentacoes_caixa.csv"'
        writer = csv.writer(response, delimiter=";")
        writer.writerow(
            [
                "Data",
                "Caixa",
                "Sessao",
                "Movimento",
                "Valor",
                "Motivo",
                "Destino/Origem",
                "Operador",
                "Terminal",
                "Status",
                "Autorizacao",
                "Autorizado por",
                "Pedido",
                "Forma",
            ]
        )
        for row in CashMovementSerializer(queryset, many=True).data:
            writer.writerow(
                [
                    row["created_at"],
                    row.get("cash_station_name") or "",
                    row["cash_register"],
                    MOVEMENT_LABELS.get(row["movement_type"], row["movement_type"]),
                    row["amount"],
                    row["reason"],
                    row["destination"],
                    row["operator_name"],
                    row["terminal_label"],
                    row["status"],
                    AUTHORIZATION_LABELS.get(row["authorization"], row["authorization"]),
                    row["authorized_by_name"],
                    row.get("order_sequence") or "",
                    row.get("payment_method_name") or "",
                ]
            )
        return response
