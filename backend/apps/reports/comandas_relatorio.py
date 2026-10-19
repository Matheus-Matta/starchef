"""`GET /reports/commands/` — o relatório de comandas (ver os dois módulos).

`now` e `open_commands` são o salão neste instante (`comandas_agora.py`) e não
dependem do período; `period` e `by_command` são o filtro de datas
(`comandas_periodo.py`). O CSV traz as comandas em uso, que é o que o gerente
leva para conferir no salão.
"""
import csv

from django.http import HttpResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports import comandas_agora, comandas_periodo
from apps.reports.cash_movements import _period
from apps.reports.views import TenantReportMixin


class CommandsReportView(TenantReportMixin, APIView):
    def get(self, request):
        try:
            inicio, fim = _period(request)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        escopo = self.tenant_filter()
        em_uso = comandas_agora.lista(escopo)
        if request.query_params.get("export") == "csv":
            return _csv(em_uso)
        return Response({
            "now": comandas_agora.resumo(escopo),
            "open_commands": em_uso,
            "period": comandas_periodo.resumo(escopo, inicio, fim),
            "by_command": comandas_periodo.por_comanda(escopo, inicio, fim),
        })


def _csv(linhas):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="comandas_em_uso.csv"'
    escritor = csv.writer(resposta)
    escritor.writerow(["Comanda", "Cliente", "Mesa", "Itens", "Valor", "Aberta desde",
                       "Ultimo lancamento", "Em conta aberta"])
    for linha in linhas:
        escritor.writerow([
            linha["number"], linha["customer_name"], linha["table"], linha["items"], linha["total"],
            _hora(linha["open_since"]), _hora(linha["last_launch"]),
            "sim" if linha["in_open_bill"] else "nao",
        ])
    return resposta


def _hora(valor):
    return timezone.localtime(valor).strftime("%d/%m/%Y %H:%M") if valor else ""
