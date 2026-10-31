"""A Visão Geral: um pouco de cada relatório, do dia (ou da semana, do mês).

`GET /api/v1/reports/overview/?periodo=dia|semana|mes&restaurant=<id>`

O dashboard antigo misturava hoje, sete dias e o mês na mesma tela, e quem
abria de manhã via o gráfico do mês e não o do dia. Aqui tudo responde ao
período escolhido (o dia, por padrão), menos o que é estado de AGORA: caixas
abertos e comandas em aberto.

Os placares principais de vendas e comandas vêm até zerados, porque zero
também responde uma pergunta do operador. Listas auxiliares vazias não vêm.
"""
from datetime import timedelta

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.reports import comandas_abertas, comandas_periodo, visao_geral_caixa
from apps.reports import visao_geral_estoque as estoque
from apps.reports import visao_geral_vendas as vendas
from apps.reports.dashboard import inicio_do_dia
from apps.reports.filter_options import report_filter_options
from apps.reports.views import TenantReportMixin
from apps.reports.visao_geral_periodo import faixa, periodo


def _sem_zeros(dados):
    """Tira o que não tem valor: 0, R$ 0,00, lista vazia, dicionário vazio."""
    limpo = {}
    for chave, valor in dados.items():
        if isinstance(valor, dict):
            valor = _sem_zeros(valor)
        if valor in (None, 0, "", [], {}) or (hasattr(valor, "is_zero") and valor.is_zero()):
            continue
        limpo[chave] = valor
    return limpo


class VisaoGeralView(TenantReportMixin, APIView):
    def get(self, request):
        from apps.orders.models import Order, OrderItem
        from apps.payments.models import Payment

        nome, primeiro, ultimo = periodo(request.query_params.get("periodo"))
        escopo = self.tenant_filter()
        pedidos = Order.objects.filter(**escopo, **faixa("opened_at", primeiro, ultimo))
        pagos = pedidos.filter(payment_status=Order.PAYMENT_PAID)
        pagamentos = Payment.objects.filter(**escopo, status=Payment.STATUS_APPROVED,
                                            **faixa("paid_at", primeiro, ultimo))
        itens_pagos = OrderItem.objects.filter(order__in=pagos).exclude(
            status__in=[OrderItem.STATUS_CANCELLED, OrderItem.STATUS_COMPED])
        fim = inicio_do_dia(ultimo + timedelta(days=1)) - timedelta(microseconds=1)
        comandas_pagas = comandas_periodo.resumo(escopo, inicio_do_dia(primeiro), fim)
        abertas = comandas_abertas.resumo(escopo)
        resumo_vendas = vendas.totais(pedidos, Order)
        resumo_comandas = {
            "em_uso": abertas["open_commands_count"],
            "em_uso_valor": abertas["open_commands_total"],
            "pagas": comandas_pagas["paid"],
            "pagas_valor": comandas_pagas["paid_total"],
            "ticket_medio": comandas_pagas["average_ticket"],
            "usadas": comandas_pagas["used"],
            "itens_lancados": comandas_pagas["launched_items"],
            "itens_lancados_valor": comandas_pagas["launched_total"],
            "tempo_medio_minutos": comandas_pagas["average_stay_minutes"],
            "itens_perdidos": comandas_pagas["lost_items"],
            "perdas_valor": comandas_pagas["lost_total"],
        }

        return Response({
            "periodo": {"nome": nome, "de": primeiro, "ate": ultimo},
            "options": report_filter_options(request, "overview", escopo),
            # Estes dois blocos são o placar principal e permanecem até
            # zerados: zero também responde uma pergunta operacional.
            "vendas": resumo_vendas,
            "comandas": resumo_comandas,
            **_sem_zeros({
                "formas_de_pagamento": vendas.formas_de_pagamento(pagamentos),
                "grafico": vendas.grafico(pagos, nome, primeiro, ultimo),
                "produtos_vendidos": estoque.produtos_vendidos(itens_pagos),
                "baixas_de_estoque": estoque.baixas_de_estoque(escopo, primeiro, ultimo),
                "caixas_abertos": visao_geral_caixa.caixas_abertos(escopo),
            }),
        })
