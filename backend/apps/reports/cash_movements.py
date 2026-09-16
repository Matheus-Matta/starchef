"""Relatorio de movimentacao do caixa: a gaveta ao longo do periodo.

Responde as perguntas que a sessao sozinha nao responde — quanto saiu em
sangria na semana, qual caixa fecha com diferenca, quem lancou o que — e
entrega tudo num CSV. So movimentos APROVADOS entram nas somas; os pendentes
aparecem contados a parte, porque ainda nao sao dinheiro que se moveu.
"""

import csv
from datetime import datetime, time

from django.db.models import Count, Q, Sum
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.payments.models import CashMovement, CashRegister
from apps.payments.serializers import CashMovementSerializer
from apps.payments.terminals import operator_label
from apps.payments.views_cash_movements import AUTHORIZATION_LABELS, MOVEMENT_LABELS
from apps.reports.views import TenantReportMixin


def _period(request):
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    parsed_from = parse_date(date_from) if date_from else None
    parsed_to = parse_date(date_to) if date_to else None
    if (date_from and not parsed_from) or (date_to and not parsed_to):
        raise ValueError("Período inválido. Use datas no formato AAAA-MM-DD.")
    if parsed_from and parsed_to and parsed_from > parsed_to:
        raise ValueError("A data inicial não pode ser posterior à data final.")
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(parsed_from, time.min), tz) if parsed_from else None
    end = timezone.make_aware(datetime.combine(parsed_to, time.max), tz) if parsed_to else None
    return start, end


def _between(field, start, end):
    filters = {}
    if start:
        filters[f"{field}__gte"] = start
    if end:
        filters[f"{field}__lte"] = end
    return filters


class CashMovementsReportView(TenantReportMixin, APIView):
    def get(self, request):
        # O caixa e do restaurante, nao da filial: a sessao pode nascer sem
        # filial (caixa fisico compartilhado), e filtrar por ela sumia com tudo.
        filters = {k: v for k, v in self.tenant_filter().items() if k != "branch_id"}
        try:
            start, end = _period(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        movements = (
            self.tenant_manager(CashMovement)
            .filter(**filters, **_between("created_at", start, end))
            .select_related(
                "cash_register__cash_station",
                "cash_register__opened_terminal",
                "operator",
                "authorized_by",
                "payment__order",
                "payment__payment_method",
            )
        )
        station = request.query_params.get("cash_station")
        operator = request.query_params.get("operator")
        movement_type = request.query_params.get("movement_type")
        if station:
            movements = movements.filter(cash_register__cash_station_id=station)
        if operator:
            movements = movements.filter(operator_id=operator)
        if movement_type:
            movements = movements.filter(movement_type=movement_type)
        approved = movements.filter(status="approved")

        def total(queryset):
            return queryset.aggregate(value=Sum("amount"))["value"] or 0

        # Retirada e negativa no banco; no relatorio cada rubrica sai positiva.
        withdrawals = approved.filter(movement_type=CashMovement.TYPE_WITHDRAWAL)
        summary = {
            "opening": total(approved.filter(movement_type=CashMovement.TYPE_OPENING)),
            "cash_sales": total(approved.filter(movement_type=CashMovement.TYPE_SALE)),
            "supplies": total(approved.filter(movement_type=CashMovement.TYPE_SUPPLY)),
            "withdrawals": -total(withdrawals.filter(payment__isnull=True)),
            "change_given": -total(withdrawals.filter(payment__isnull=False)),
            "refunds": -total(approved.filter(movement_type=CashMovement.TYPE_REFUND)),
            "adjustments": total(approved.filter(movement_type=CashMovement.TYPE_ADJUSTMENT)),
            "net": total(approved),
            "movements_count": movements.count(),
            "pending_count": movements.filter(status="pending").count(),
        }

        by_type = [
            {
                "movement_type": row["movement_type"],
                "label": MOVEMENT_LABELS.get(row["movement_type"], row["movement_type"]),
                "count": row["count"],
                "total": row["total"] or 0,
            }
            for row in approved.values("movement_type").annotate(count=Count("id"), total=Sum("amount")).order_by("movement_type")
        ]
        by_station = [
            {
                "cash_station": row["cash_register__cash_station_id"],
                "cash_station_name": row["cash_register__cash_station__name"] or "Sem caixa",
                "count": row["count"],
                "total": row["total"] or 0,
                "withdrawals": -(row["withdrawals"] or 0),
                "supplies": row["supplies"] or 0,
            }
            for row in approved.values("cash_register__cash_station_id", "cash_register__cash_station__name")
            .annotate(
                count=Count("id"),
                total=Sum("amount"),
                withdrawals=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_WITHDRAWAL, payment__isnull=True)),
                supplies=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_SUPPLY)),
            )
            .order_by("cash_register__cash_station__name")
        ]
        by_operator = [
            {
                "operator": row["operator_id"],
                "operator_name": (f"{row['operator__first_name']} {row['operator__last_name']}".strip() or row["operator__username"]),
                "count": row["count"],
                "total": row["total"] or 0,
                "withdrawals": -(row["withdrawals"] or 0),
                "supplies": row["supplies"] or 0,
            }
            for row in approved.values("operator_id", "operator__first_name", "operator__last_name", "operator__username")
            .annotate(
                count=Count("id"),
                total=Sum("amount"),
                withdrawals=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_WITHDRAWAL, payment__isnull=True)),
                supplies=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_SUPPLY)),
            )
            .order_by("-count")
        ]
        by_day = [
            {
                "day": row["day"].isoformat() if row["day"] else None,
                "count": row["count"],
                "cash_sales": row["cash_sales"] or 0,
                "withdrawals": -(row["withdrawals"] or 0),
                "supplies": row["supplies"] or 0,
            }
            for row in approved.annotate(day=TruncDate("created_at"))
            .values("day")
            .annotate(
                count=Count("id"),
                cash_sales=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_SALE)),
                withdrawals=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_WITHDRAWAL, payment__isnull=True)),
                supplies=Sum("amount", filter=Q(movement_type=CashMovement.TYPE_SUPPLY)),
            )
            .order_by("day")
        ]

        sessions_qs = (
            self.tenant_manager(CashRegister)
            .filter(**filters, **_between("opened_at", start, end))
            .select_related("cash_station", "opened_by", "closed_by")
            .order_by("-opened_at")
        )
        if station:
            sessions_qs = sessions_qs.filter(cash_station_id=station)
        if operator:
            sessions_qs = sessions_qs.filter(opened_by_id=operator)
        sessions = [
            {
                "id": str(session.pk),
                "cash_station_name": session.cash_station.name if session.cash_station_id else "",
                "operator_name": operator_label(session.opened_by) if session.opened_by_id else "",
                "terminal_label": session.opened_terminal_label or "",
                "opened_at": session.opened_at,
                "closed_at": session.closed_at,
                "status": session.status,
                "opening_amount": session.opening_amount,
                "expected_amount": session.expected_amount,
                "actual_amount": session.actual_amount,
                "difference_amount": session.difference_amount,
            }
            for session in sessions_qs
        ]
        finished = [s for s in sessions if s["status"] in {CashRegister.STATUS_CLOSED, CashRegister.STATUS_CLOSED_DIFFERENCE}]
        summary["sessions_count"] = len(sessions)
        summary["sessions_with_difference"] = sum(1 for s in finished if s["status"] == CashRegister.STATUS_CLOSED_DIFFERENCE)
        summary["difference_total"] = sum((s["difference_amount"] or 0) for s in finished)

        page = self._positive_int(request.query_params.get("page"), 1)
        page_size = min(self._positive_int(request.query_params.get("page_size"), 20), 200)
        ordered = movements.order_by("-created_at")
        count = ordered.count()
        rows = CashMovementSerializer(ordered[(page - 1) * page_size : page * page_size], many=True).data

        data = {
            "summary": summary,
            "by_type": by_type,
            "by_station": by_station,
            "by_operator": by_operator,
            "by_day": by_day,
            "sessions": sessions,
            "movements": rows,
            "pagination": {
                "movements": {"page": page, "page_size": page_size, "count": count, "pages": max(1, (count + page_size - 1) // page_size)}
            },
            "filters": {
                "date_from": request.query_params.get("date_from"),
                "date_to": request.query_params.get("date_to"),
                "restaurant": request.query_params.get("restaurant"),
                "cash_station": station,
                "operator": operator,
                "movement_type": movement_type,
            },
        }
        if request.query_params.get("export") == "csv":
            return self._csv(data, CashMovementSerializer(ordered[:5000], many=True).data)
        return Response(data)

    @staticmethod
    def _positive_int(value, default):
        try:
            parsed = int(value)
            return parsed if parsed > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _csv(data, movements):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        filters = data["filters"]
        response["Content-Disposition"] = (
            f'attachment; filename="caixa_{filters["date_from"] or "inicio"}_{filters["date_to"] or "hoje"}.csv"'
        )
        writer = csv.writer(response, delimiter=";")
        summary = data["summary"]
        writer.writerow(["StarChef — Movimentação do caixa"])
        writer.writerow([f"Período: {filters['date_from'] or 'início'} a {filters['date_to'] or 'hoje'}"])
        for key, label in [
            ("opening", "Aberturas"),
            ("cash_sales", "Vendas em dinheiro"),
            ("supplies", "Suprimentos"),
            ("withdrawals", "Sangrias"),
            ("change_given", "Troco de outras formas"),
            ("refunds", "Estornos"),
            ("net", "Saldo líquido"),
            ("difference_total", "Diferença acumulada nos fechamentos"),
        ]:
            writer.writerow([label, summary[key]])
        writer.writerow([])
        writer.writerow(["Sessões"])
        writer.writerow(["Caixa", "Operador", "Terminal", "Abertura", "Fechamento", "Status", "Troco inicial", "Esperado", "Contado", "Diferença"])
        for s in data["sessions"]:
            writer.writerow(
                [
                    s["cash_station_name"], s["operator_name"], s["terminal_label"], s["opened_at"], s["closed_at"] or "",
                    s["status"], s["opening_amount"], s["expected_amount"], s["actual_amount"] if s["actual_amount"] is not None else "",
                    s["difference_amount"] if s["difference_amount"] is not None else "",
                ]
            )
        writer.writerow([])
        writer.writerow(["Movimentos"])
        writer.writerow(["Data", "Caixa", "Movimento", "Valor", "Motivo", "Destino/Origem", "Operador", "Terminal", "Status", "Autorização", "Autorizado por", "Pedido", "Forma"])
        for row in movements:
            writer.writerow(
                [
                    row["created_at"], row.get("cash_station_name") or "", MOVEMENT_LABELS.get(row["movement_type"], row["movement_type"]),
                    row["amount"], row["reason"], row["destination"], row["operator_name"], row["terminal_label"], row["status"],
                    AUTHORIZATION_LABELS.get(row["authorization"], row["authorization"]), row["authorized_by_name"],
                    row.get("order_sequence") or "", row.get("payment_method_name") or "",
                ]
            )
        return response
