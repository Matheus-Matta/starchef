"""Quando um cardápio de consumo vence: todo dia, em dias da semana ou no mês."""
import calendar
from datetime import timedelta

from apps.cardapio_consumo.models import CardapioConsumo


def dia_do_mes_efetivo(dia, data):
    """O dia escolhido, ou o último do mês quando ele não existe ali.

    "Todo dia 31" cai em 28/29 de fevereiro e em 30 de abril: nenhum mês fica
    sem a baixa (decisão do dono, 2026-11-08).
    """
    return min(int(dia), calendar.monthrange(data.year, data.month)[1])


def vence_em(cardapio, data):
    if not cardapio.ativo or data < cardapio.comeca_em:
        return False
    if cardapio.frequencia == CardapioConsumo.DIARIA:
        return True
    if cardapio.frequencia == CardapioConsumo.SEMANAL:
        return data.weekday() in {int(dia) for dia in (cardapio.dias_da_semana or [])}
    if cardapio.frequencia == CardapioConsumo.MENSAL and cardapio.dia_do_mes:
        return data.day == dia_do_mes_efetivo(cardapio.dia_do_mes, data)
    return False


DIAS = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]


def descricao(cardapio):
    """"Toda terça e quinta, às 06:00" — para a lista do painel."""
    hora = f"às {cardapio.horario:%H:%M}"
    if cardapio.frequencia == CardapioConsumo.SEMANAL:
        nomes = [DIAS[int(dia)] for dia in sorted(cardapio.dias_da_semana or [])]
        dias = " e ".join([", ".join(nomes[:-1]), nomes[-1]] if len(nomes) > 1 else nomes)
        return f"Toda {dias}, {hora}" if dias else "Semanal sem dia escolhido"
    if cardapio.frequencia == CardapioConsumo.MENSAL:
        return f"Todo dia {cardapio.dia_do_mes} do mês, {hora}"
    return f"Todo dia, {hora}"


def proximas_datas(cardapio, a_partir_de, quantas=3, limite_em_dias=400):
    """As próximas datas em que o cardápio vence — para a tela mostrar."""
    datas = []
    data = a_partir_de
    for _ in range(limite_em_dias):
        if vence_em(cardapio, data):
            datas.append(data)
            if len(datas) == quantas:
                break
        data += timedelta(days=1)
    return datas
