"""Quantas vezes cada forma de pagamento foi usada — para a mais usada vir antes.

O PDV abria o pagamento com a forma da ordem de cadastro, e o caixa trocava
para Pix ou débito em quase toda venda. Pedindo `?ordering=-uso,name`, a lista
vem pela contagem de recebimentos APROVADOS dos últimos 90 dias: estorno não é
uso, e o hábito de seis meses atrás não diz qual é o de hoje.

É uma anotação, e não uma coluna: contar na leitura não exige manter um
contador que a sincronização, o estorno e a exclusão teriam de lembrar de
atualizar.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone

JANELA = timedelta(days=90)


def anotar_uso(queryset):
    from apps.payments.models import Payment

    desde = timezone.now() - JANELA
    return queryset.annotate(
        uso=Count(
            "payments",
            filter=Q(
                payments__status=Payment.STATUS_APPROVED,
                payments__paid_at__gte=desde,
                payments__deleted_at__isnull=True,
            ),
        )
    )
