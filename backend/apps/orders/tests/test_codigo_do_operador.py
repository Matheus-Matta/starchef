"""O código de quem lançou, num aparelho compartilhado.

O caso é o totem no salão: uma sessão só, vários garçons. Sem o código, todo
lançamento do dia fica no nome do mesmo login e a pergunta "quem anotou isso?"
deixa de ter resposta.

O que estes testes fixam é a fronteira do que o código É: ATRIBUIÇÃO. Ele não
autentica ninguém e não autoriza nada — qualquer número passa, de propósito, e a
política de quais números valem é interna do restaurante.
"""

import uuid
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from apps.core.tenant import tenant_context
from apps.menu.models import Product
from apps.orders.models import Order
from apps.orders.operator_code import CHAVE, codigo_de
from apps.orders.services import add_order_item, create_order
from apps.restaurants.models import Command

pytestmark = pytest.mark.django_db


@pytest.fixture
def produto(account, restaurant, branch):
    produto = Product.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Coxinha", internal_code=f"CX-{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("8.00"),
    )
    produto.restaurants.add(restaurant)
    return produto


@pytest.fixture
def exige_codigo(restaurant):
    restaurant.require_operator_code = True
    restaurant.save(update_fields=["require_operator_code"])
    return restaurant


def _pedido(restaurant, branch, user, **extra):
    return create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_COUNTER, user=user, **extra
    )


def test_sem_a_opcao_ligada_nada_muda(account, restaurant, branch, manager_user, produto):
    """A exigência nasce DESLIGADA: instalação que já existe não trava no deploy."""
    with tenant_context(account):
        assert restaurant.require_operator_code is False
        pedido = _pedido(restaurant, branch, manager_user)
        item = add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
        assert item.metafields == {}


def test_com_a_opcao_ligada_abrir_pedido_sem_codigo_e_recusado(
    account, exige_codigo, branch, manager_user
):
    with tenant_context(account), pytest.raises(ValidationError) as falha:
        _pedido(exige_codigo, branch, manager_user)
    assert "código do operador" in str(falha.value)
    assert "abrir pedido" in str(falha.value)


def test_o_codigo_grava_no_pedido_e_o_item_herda(
    account, exige_codigo, branch, manager_user, produto
):
    """O item herda o código do pedido: o garçom digita UMA vez por atendimento.

    Cobrar a cada prato faria ele digitar dez vezes na mesma mesa — e a décima
    seria "1111" para acabar logo.
    """
    with tenant_context(account):
        pedido = _pedido(exige_codigo, branch, manager_user, metafields={CHAVE: "4821"})
        assert codigo_de(pedido.metafields) == "4821"

        item = add_order_item(order=pedido, product=produto, quantity=1, user=manager_user)
        assert codigo_de(item.metafields) == "4821"


def test_o_item_pode_trazer_codigo_proprio_e_ele_vence(
    account, exige_codigo, branch, manager_user, produto
):
    """Outro garçom lançou no mesmo pedido: o item registra QUEM lançou.

    É o ponto do desenho. Num pedido de uma hora, três pessoas anotam, e um
    código só no cabeçalho atribuiria tudo ao primeiro.
    """
    with tenant_context(account):
        pedido = _pedido(exige_codigo, branch, manager_user, metafields={CHAVE: "1001"})
        item = add_order_item(
            order=pedido, product=produto, quantity=1, user=manager_user,
            metafields={CHAVE: "2002"},
        )
        assert codigo_de(item.metafields) == "2002"
        # O cabeçalho do pedido não é reescrito: quem abriu a conta abriu.
        pedido.refresh_from_db()
        assert codigo_de(pedido.metafields) == "1001"


def test_o_pedido_herda_os_campos_da_comanda(account, exige_codigo, branch, manager_user):
    """O cartão é aberto no salão e o pedido só nasce no caixa, horas depois."""
    with tenant_context(account):
        comanda = Command.objects.create(
            account=account, restaurant=exige_codigo, branch=branch,
            number=9001, metafields={CHAVE: "7777", "turno": "noite"},
        )
        pedido = create_order(
            restaurant=exige_codigo, branch=branch, order_type=Order.TYPE_COMMAND,
            user=manager_user, command=comanda,
        )
        # Sem informar código nenhum: ele veio do cartão, e por isso a abertura
        # não foi recusada.
        assert codigo_de(pedido.metafields) == "7777"
        assert pedido.metafields["turno"] == "noite"


def test_o_que_vem_no_pedido_vence_o_da_comanda(account, exige_codigo, branch, manager_user):
    """Mais recente e mais específico ganha — senão o rastro do caixa se perderia."""
    with tenant_context(account):
        comanda = Command.objects.create(
            account=account, restaurant=exige_codigo, branch=branch,
            number=9002, metafields={CHAVE: "1111"},
        )
        pedido = create_order(
            restaurant=exige_codigo, branch=branch, order_type=Order.TYPE_COMMAND,
            user=manager_user, command=comanda, metafields={CHAVE: "2222"},
        )
        assert codigo_de(pedido.metafields) == "2222"


def test_o_codigo_aceita_apenas_numeros(account, exige_codigo, branch, manager_user):
    """Letra e acento num totem viram dois registros para a mesma pessoa."""
    with tenant_context(account), pytest.raises(ValidationError) as falha:
        _pedido(exige_codigo, branch, manager_user, metafields={CHAVE: "joão"})
    assert "apenas números" in str(falha.value)


def test_o_codigo_nao_precisa_existir_em_cadastro_nenhum(
    account, exige_codigo, branch, manager_user
):
    """É atribuição, não autenticação: qualquer número passa, de propósito.

    Exigir cadastro transformaria uma medida de rastro em mais um cadastro para o
    restaurante manter — e no dia em que o garçom novo entrasse, ele não poderia
    lançar.
    """
    with tenant_context(account):
        pedido = _pedido(exige_codigo, branch, manager_user, metafields={CHAVE: "999999"})
        assert codigo_de(pedido.metafields) == "999999"


def test_a_nota_mostra_o_operador_com_o_codigo(
    account, exige_codigo, branch, manager_user, produto
):
    """`Operador: Nome - 4821`, a linha que o cupom imprime."""
    with tenant_context(account):
        pedido = _pedido(exige_codigo, branch, manager_user, metafields={CHAVE: "4821"})
        pedido.refresh_from_db()
        nome = manager_user.get_full_name() or manager_user.username
        assert pedido.operator_label == f"{nome} - 4821"


def test_sem_codigo_a_nota_mostra_so_o_nome(account, restaurant, branch, manager_user):
    """Restaurante que não usa a opção imprime o cupom como sempre imprimiu."""
    with tenant_context(account):
        pedido = _pedido(restaurant, branch, manager_user)
        pedido.refresh_from_db()
        nome = manager_user.get_full_name() or manager_user.username
        assert pedido.operator_label == nome
