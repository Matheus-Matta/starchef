"""Quando o cardápio vence: todo dia, nos dias da semana, no dia do mês."""
from datetime import date

from apps.cardapio_consumo.agenda import proximas_datas, vence_em
from apps.cardapio_consumo.models import CardapioConsumo

SEGUNDA = date(2026, 11, 9)


def _cardapio(**campos):
    campos.setdefault("comeca_em", date(2026, 1, 1))
    return CardapioConsumo(nome="x", **campos)


def test_semanal_vence_so_nos_dias_escolhidos():
    terca_e_quinta = _cardapio(frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[1, 3])
    assert [vence_em(terca_e_quinta, date(2026, 11, dia)) for dia in range(9, 16)] == [
        False, True, False, True, False, False, False]


def test_dia_31_cai_no_ultimo_dia_do_mes_que_nao_tem_31():
    """Decisão do dono: nenhum mês fica sem a baixa mensal."""
    dia_31 = _cardapio(frequencia=CardapioConsumo.MENSAL, dia_do_mes=31)
    assert vence_em(dia_31, date(2026, 2, 28))
    assert not vence_em(dia_31, date(2026, 2, 27))
    assert vence_em(dia_31, date(2028, 2, 29))
    assert vence_em(dia_31, date(2026, 4, 30))
    assert vence_em(dia_31, date(2026, 1, 31)) and not vence_em(dia_31, date(2026, 1, 30))


def test_nao_vence_antes_do_inicio_nem_desligado():
    """Criado hoje para começar segunda: não pode baixar hoje à tarde."""
    diario = _cardapio(frequencia=CardapioConsumo.DIARIA, comeca_em=SEGUNDA)
    assert not vence_em(diario, date(2026, 11, 8)) and vence_em(diario, SEGUNDA)
    diario.ativo = False
    assert not vence_em(diario, SEGUNDA)


def test_descricao_legivel_para_a_lista():
    from datetime import time

    from apps.cardapio_consumo.agenda import descricao

    semanal = _cardapio(frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[3, 0, 1], horario=time(6, 30))
    assert descricao(semanal) == "Toda segunda, terça e quinta, às 06:30"
    assert descricao(_cardapio(frequencia=CardapioConsumo.MENSAL, dia_do_mes=31, horario=time(7, 0))) == (
        "Todo dia 31 do mês, às 07:00")


def test_proximas_datas_para_a_tela():
    semanal = _cardapio(frequencia=CardapioConsumo.SEMANAL, dias_da_semana=[0])
    assert proximas_datas(semanal, date(2026, 11, 10), 2) == [date(2026, 11, 16), date(2026, 11, 23)]
