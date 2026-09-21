"""A loja e a nuvem numeram pedido em faixas que NUNCA se encontram.

Os dois backends atendem o mesmo restaurante, e enquanto a loja está fora ela
não enxerga o que a nuvem emitiu. Sem faixas, as duas entregam o mesmo número
— e quando a sincronização junta as bases, dois pedidos diferentes têm o
"pedido 17". A conferência de caixa do dia não fecha, e ninguém consegue dizer
qual é qual.
"""
import pytest

from apps.core.tenant import tenant_context
from apps.orders import sequence_ranges
from apps.orders.models import Order
from apps.orders.sequence_ranges import PRIMEIRO_NUMERO_DA_NUVEM, proximo_numero


@pytest.fixture
def como_loja(settings):
    settings.SYNC_NODE_TYPE = "local"


@pytest.fixture
def como_nuvem(settings):
    settings.SYNC_NODE_TYPE = "cloud"


def _proximo(restaurant):
    """O próximo número, dentro do contexto do tenant.

    O gerente dos models é filtrado por conta: fora do contexto, o queryset
    vem vazio e a numeração recomeçaria do piso — que é justamente o defeito
    que estes testes existem para pegar.
    """
    with tenant_context(restaurant.account):
        return proximo_numero(Order.objects.filter(restaurant=restaurant))


def _pedido(restaurant, branch, user, numero):
    return Order.objects.create(
        account=restaurant.account,
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        sequence=numero,
        created_by=user,
        updated_by=user,
    )


@pytest.mark.django_db
def test_a_loja_comeca_no_um(como_loja, restaurant, branch, manager_user):
    """O número é lido em voz alta: "pedido 42" cabe no cupom e na boca."""
    assert _proximo(restaurant) == 1


@pytest.mark.django_db
def test_a_nuvem_comeca_na_faixa_alta(como_nuvem, restaurant, branch, manager_user):
    """E o número alto denuncia sozinho: este pedido nasceu numa queda."""
    assert (
        _proximo(restaurant)
        == PRIMEIRO_NUMERO_DA_NUVEM
    )


@pytest.mark.django_db
def test_a_loja_IGNORA_o_que_a_nuvem_emitiu(
    como_loja, restaurant, branch, manager_user
):
    """O defeito que a faixa existe para impedir.

    A loja volta, recebe da nuvem o pedido 1.000.005, e sem o recorte passaria
    a numerar a partir dele — abandonando a própria faixa e indo colidir com a
    nuvem no pedido seguinte.
    """
    _pedido(restaurant, branch, manager_user, 42)
    _pedido(restaurant, branch, manager_user, PRIMEIRO_NUMERO_DA_NUVEM + 5)

    assert _proximo(restaurant) == 43


@pytest.mark.django_db
def test_a_loja_nao_volta_ao_um_por_causa_do_recorte(
    como_loja, restaurant, branch, manager_user
):
    """O erro do outro lado, igualmente sutil.

    Zerar quando o máximo GLOBAL está fora da faixa faria a loja voltar ao
    número 1 e colidir com os PRÓPRIOS pedidos.
    """
    _pedido(restaurant, branch, manager_user, 7)
    _pedido(restaurant, branch, manager_user, PRIMEIRO_NUMERO_DA_NUVEM + 900)

    assert _proximo(restaurant) == 8


@pytest.mark.django_db
def test_a_nuvem_ignora_o_que_a_loja_emitiu(
    como_nuvem, restaurant, branch, manager_user
):
    _pedido(restaurant, branch, manager_user, 42)
    _pedido(restaurant, branch, manager_user, PRIMEIRO_NUMERO_DA_NUVEM + 5)

    assert (
        _proximo(restaurant)
        == PRIMEIRO_NUMERO_DA_NUVEM + 6
    )


@pytest.mark.django_db
def test_as_duas_faixas_nunca_se_encontram(
    restaurant, branch, manager_user, settings
):
    """A propriedade que importa, afirmada de ponta a ponta.

    Cada nó emite dez pedidos sem enxergar o outro — que é exatamente o que
    acontece com a loja fora do ar — e nenhum número se repete.
    """
    numeros = set()
    for tipo in ("local", "cloud"):
        settings.SYNC_NODE_TYPE = tipo
        for _ in range(10):
            numero = _proximo(restaurant)
            assert numero not in numeros, f"{tipo} repetiu o número {numero}"
            numeros.add(numero)
            _pedido(restaurant, branch, manager_user, numero)

    assert len(numeros) == 20


@pytest.mark.django_db
def test_sem_a_variavel_o_no_se_comporta_como_loja(restaurant, settings):
    """Na dúvida, a faixa é a da loja.

    Quase toda instalação é loja, e um nó que se achasse nuvem por engano
    numeraria na faixa alta sem necessidade — assustando quem lê o cupom.
    """
    settings.SYNC_NODE_TYPE = ""

    assert sequence_ranges.e_a_nuvem() is False
    assert _proximo(restaurant) == 1
