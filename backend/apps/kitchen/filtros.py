"""Filtros do KDS."""
from datetime import timedelta

import django_filters

from apps.core.periodo import inicio_do_dia
from apps.orders.models import OrderItem


class KitchenItemFilter(django_filters.FilterSet):
    """Filtro do KDS: setor/status + intervalo de datas (por data de lançamento).

    O dia vira INTERVALO de instantes, e não `launched_at__date`: a função de
    data aplicada na coluna impedia o Postgres de usar índice, e cada leitura
    do quadro (a cada poucos segundos, por tela de KDS) varria a tabela de
    itens inteira — que só cresce, dia após dia.
    """

    launched_after = django_filters.DateFilter(method="_a_partir_de")
    launched_before = django_filters.DateFilter(method="_ate")

    def _a_partir_de(self, queryset, name, value):
        return queryset.filter(launched_at__gte=inicio_do_dia(value))

    def _ate(self, queryset, name, value):
        return queryset.filter(launched_at__lt=inicio_do_dia(value + timedelta(days=1)))

    class Meta:
        model = OrderItem
        fields = ["production_sector", "status"]
