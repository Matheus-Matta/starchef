"""Na carga e na recuperação, o recebimento chega antes do troco dele.

`cash_movement.payment` aponta para o recebimento (a venda em dinheiro e o
troco de uma venda no cartão), mas o catálogo só declarava `cash_register`. Na
ordem topológica o movimento vinha ANTES do recebimento: todo troco falhava
com "Payment ... ainda não existe aqui" e dependia da escada de retentativa
para entrar — e um troco que não entra é dinheiro que some do esperado do
outro lado (relato: R$ 50 de troco de um débito fora do extrato da nuvem).
"""
from apps.synchronization.services.registry import registry


def test_recebimento_vem_antes_do_movimento_de_caixa_na_ordem_de_carga():
    ordem = [entrada.entity_type for entrada in registry.ordered()]

    assert ordem.index("payment") < ordem.index("cash_movement")
    assert "payment" in registry.require("cash_movement").dependencies
