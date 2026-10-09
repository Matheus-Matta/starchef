"""Item de pedido, pedido, pagamento e caixa nunca cedem o lugar em silêncio.

A adoção APAGA a linha local para dar lugar à da origem. Para o item de pedido
isso escondia dinheiro em dobro: a mesma comanda cobrada na loja e na nuvem
durante uma queda, e na chegada a nuvem apagava os itens do pedido DELA — que
ficava pago, com o valor, e sem item nenhum (simulação do dia a dia,
`loadtest/dia_a_dia`: três pedidos, R$ 1.495,07). Colisão de dinheiro vira
conflito aberto, para alguém estornar.
"""
import pytest

from apps.synchronization.constants import NodeType
from apps.synchronization.services import adoption


@pytest.mark.parametrize("entidade", ["order", "order_item", "order_item_addon", "payment",
                                      "cash_register", "cash_movement"])
@pytest.mark.parametrize("recebe", [NodeType.LOCAL, NodeType.CLOUD])
def test_dinheiro_nunca_e_adotado(entidade, recebe):
    assert adoption.origin_is_authority(entidade, recebe) is False
