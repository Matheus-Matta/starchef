"""A leitura da balança recebe o item da comanda DEPOIS de nascer.

Ela era `immutable` ("append-only"): o destino inseria e ignorava qualquer
atualização. Mas a leitura é criada e só então ligada ao item em que virou
(`command_item`). Na nuvem, toda leitura ficava sem item — achado pela
simulação do dia a dia (`loadtest/dia_a_dia`), 17 de 17 leituras diferentes.
"""
from apps.synchronization.services.registry import registry


def test_leitura_da_balanca_aceita_atualizacao():
    assert registry.require("scale_reading").immutable is False
