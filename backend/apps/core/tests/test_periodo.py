"""`filtro_de_dias`: o mesmo resultado do `__date`, sem função sobre a coluna."""
from datetime import date, datetime, time, timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.periodo import filtro_de_dias
from apps.orders.models import Order
from apps.orders.services import create_order


def test_intervalo_cobre_o_dia_inteiro_no_fuso_da_loja():
    filtros = filtro_de_dias("opened_at", date(2026, 11, 1), "2026-11-03")

    inicio, fim = filtros["opened_at__gte"], filtros["opened_at__lt"]
    assert timezone.localtime(inicio).replace(tzinfo=None) == datetime(2026, 11, 1)
    assert timezone.localtime(fim).replace(tzinfo=None) == datetime(2026, 11, 4)


def test_sem_datas_nao_filtra():
    assert filtro_de_dias("opened_at") == {}
    assert filtro_de_dias("opened_at", "", None) == {}


@pytest.mark.parametrize("lixo", ["2026-13-45", "ontem", "abc"])
def test_data_invalida_e_erro_de_validacao(lixo):
    with pytest.raises(ValidationError):
        filtro_de_dias("opened_at", lixo)


@pytest.mark.django_db
def test_mesma_contagem_que_o_date_e_sem_cast_no_sql(account, restaurant, branch, manager_user):
    dia = date(2026, 11, 10)
    meia_noite = timezone.make_aware(datetime.combine(dia, time.min))
    for quando in (meia_noite - timedelta(seconds=1), meia_noite, meia_noite + timedelta(hours=23, minutes=59),
                   meia_noite + timedelta(days=1)):
        pedido = create_order(restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=manager_user)
        Order.all_objects.filter(pk=pedido.pk).update(opened_at=quando)
    novo = Order.all_objects.filter(account=account, **filtro_de_dias("opened_at", dia, dia))
    antigo = Order.all_objects.filter(account=account, opened_at__date__gte=dia, opened_at__date__lte=dia)

    assert novo.count() == antigo.count() == 2
    sql = str(novo.query).lower()
    assert "::date" not in sql and "cast_date" not in sql
