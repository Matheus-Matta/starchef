"""A opção "troco só em dinheiro" do restaurante chega ao outro servidor.

Campo novo não tem trava automática: sem estar no payload, a loja continuaria
dando troco no cartão depois de a nuvem desligar — e o PDV, que lê o
restaurante do servidor em que está, obedeceria a cada um de um jeito.
"""
from apps.restaurants.models import Restaurant
from apps.synchronization.services import serialization
from apps.synchronization.services.registry import registry


def test_allow_change_on_non_cash_viaja_no_evento_do_restaurante(conta):
    restaurante = Restaurant.objects.create(account=conta, legal_name="T LTDA", trade_name="T",
                                            allow_change_on_non_cash=False)

    payload = serialization.build_payload(
        restaurante, registry.require("restaurant"), origin_node_id="nuvem")

    assert payload["fields"]["allow_change_on_non_cash"] is False
