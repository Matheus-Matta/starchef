"""Filtro por DIA que usa índice.

`campo__date__gte=dia` vira `("campo" AT TIME ZONE ...)::date >= dia` no
Postgres: uma função sobre a coluna, que o índice em `campo` não atende — o
banco lê a tabela inteira. Com meses de histórico, o relatório do dia fica tão
lento quanto o do ano (foi o que travava o quadro do KDS).

O mesmo dia como INTERVALO de instantes (`campo >= meia-noite` e
`campo < meia-noite do dia seguinte`, no fuso corrente — o mesmo que o
`__date` usa) dá o mesmo resultado e usa o índice.
"""
from datetime import date, datetime, time, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.dateparse import parse_date


def inicio_do_dia(dia):
    """Meia-noite de `dia` no fuso corrente, como instante."""
    return timezone.make_aware(datetime.combine(dia, time.min))


def _como_data(valor):
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return timezone.localtime(valor).date() if timezone.is_aware(valor) else valor.date()
    if isinstance(valor, date):
        return valor
    try:
        dia = parse_date(str(valor)[:10])
    except ValueError:
        dia = None
    if dia is None:
        raise ValidationError(f"Data inválida: {str(valor)[:20]!r}. Use AAAA-MM-DD.")
    return dia


def filtro_de_dias(campo, de=None, ate=None):
    """Kwargs de `filter()` para `de <= dia(campo) <= ate`, ambos opcionais.

    Aceita `date`, `datetime` ou texto `AAAA-MM-DD`; texto inválido levanta
    `ValidationError` (o handler da API responde 400), como o `__date` fazia.
    """
    filtros = {}
    de, ate = _como_data(de), _como_data(ate)
    if de is not None:
        filtros[f"{campo}__gte"] = inicio_do_dia(de)
    if ate is not None:
        filtros[f"{campo}__lt"] = inicio_do_dia(ate + timedelta(days=1))
    return filtros
