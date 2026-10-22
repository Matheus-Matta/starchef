"""O período da Visão Geral: hoje (padrão), esta semana ou este mês.

Sempre até HOJE, em faixa de horário (`>= início`, `< fim`) para o Postgres
usar o índice de data — ver `dashboard.faixa`. "Semana" começa na segunda e
"mês" no dia 1: é como o dono do restaurante fala ("como foi a semana?").
"""
from datetime import timedelta

from django.utils import timezone

from apps.reports.dashboard import inicio_do_dia

DIA, SEMANA, MES = "dia", "semana", "mes"
PERIODOS = (DIA, SEMANA, MES)


def periodo(nome, hoje=None):
    """`(nome, primeiro_dia, último_dia)`; nome desconhecido vira o dia."""
    hoje = hoje or timezone.localdate()
    if nome == SEMANA:
        return SEMANA, hoje - timedelta(days=hoje.weekday()), hoje
    if nome == MES:
        return MES, hoje.replace(day=1), hoje
    return DIA, hoje, hoje


def faixa(campo, primeiro, ultimo):
    return {f"{campo}__gte": inicio_do_dia(primeiro),
            f"{campo}__lt": inicio_do_dia(ultimo + timedelta(days=1))}
