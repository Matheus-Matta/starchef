"""A balança pesa para a COMANDA — e falha fechado sem cartão.

O risco desta mudança é de dinheiro: se a balança continuar amarrada depois da
pesagem, o prato do próximo cliente cai na comanda do anterior. A pessoa vai
embora, outra chega, põe o prato sem passar o cartão — e paga o almoço de um
estranho.
"""
import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.core.tenant import tenant_context
from apps.menu.models import Product, ProductCategory
from apps.orders.models import Order, OrderItem
from apps.printers.models import Printer, Scale, ScaleReading
from apps.printers.scale_command import (
    bind_command_to_scale,
    consume_command_binding,
    weigh_into_command,
)
from apps.restaurants.models import Command, TableSector

pytestmark = pytest.mark.django_db


@pytest.fixture
def contexto(account):
    """A conta corrente fora da requisição.

    O middleware LIMPA a conta ao terminar o request: depois de um `POST` pelo
    `api_client`, um `Model.objects` sem contexto devolve queryset vazio e o
    teste falha por "não existe" onde o problema é só a falta de conta. Por
    isso as conferências pós-requisição reentram no contexto.
    """
    with tenant_context(account):
        yield account



@pytest.fixture
def produto_por_kg(contexto, account, restaurant, branch):
    categoria = ProductCategory.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Self-service"
    )
    return Product.objects.create(
        account=account, restaurant=restaurant, branch=branch, category=categoria,
        name="Prato por quilo", internal_code=f"K{uuid.uuid4().hex[:6]}",
        sale_price=Decimal("59.90"), pricing_unit=Product.PRICING_KG,
    )


@pytest.fixture
def balanca_de_comanda(contexto, account, restaurant, branch, produto_por_kg):
    sector = TableSector.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Balanca"
    )
    printer = Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Balanca 1", sector=sector, is_active=True,
    )
    return Scale.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        name="Balanca do buffet", product=produto_por_kg, printer=printer,
        auto_print=True, weighing_mode=Scale.MODE_COMMAND,
    )


@pytest.fixture
def comanda(contexto, account, restaurant, branch):
    return Command.objects.create(account=account, restaurant=restaurant, branch=branch)



def _leitura(scale, peso):
    """Uma pesagem estável desta balança, pronta para virar anotação."""
    return ScaleReading.objects.create(
        account=scale.account,
        restaurant=scale.restaurant,
        branch=scale.branch,
        scale=scale,
        weight_kg=Decimal(peso),
        tare_kg=Decimal("0.000"),
        is_stable=True,
    )

def test_o_vinculo_e_consumido_na_primeira_pesagem(balanca_de_comanda, comanda, manager_user):
    """Senão o prato do próximo cliente cai na comanda do anterior."""
    bind_command_to_scale(scale=balanca_de_comanda, reference=comanda.code, user=manager_user)

    primeira = consume_command_binding(balanca_de_comanda)
    assert primeira is not None and primeira.pk == comanda.pk

    balanca_de_comanda.refresh_from_db()
    segunda = consume_command_binding(balanca_de_comanda)
    assert segunda is None, "A segunda leitura estável não pode reusar o cartão."


def test_o_vinculo_expira_por_tempo(balanca_de_comanda, comanda, manager_user):
    bind_command_to_scale(scale=balanca_de_comanda, reference=comanda.code, user=manager_user)
    balanca_de_comanda.refresh_from_db()
    balanca_de_comanda.active_command_until = timezone.now() - timedelta(seconds=1)
    balanca_de_comanda.save(update_fields=["active_command_until"])

    assert consume_command_binding(balanca_de_comanda) is None


def test_sem_cartao_no_modo_comanda_nao_nasce_pedido_de_balcao(
    balanca_de_comanda, manager_user, api_client, account
):
    """Falha fechado: um prato do cliente A não pode virar conta avulsa silenciosa."""
    pedidos_antes = Order.objects.count()

    response = api_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca_de_comanda.id), "weight_kg": "0.480", "is_stable": True},
        format="json",
    )
    assert response.status_code == 201

    with tenant_context(account):
        assert Order.objects.count() == pedidos_antes
        assert not OrderItem.objects.exists()
        leitura = ScaleReading.objects.get(pk=response.data["id"])
        # E o operador precisa VER o motivo, senão a leitura some em silêncio.
        assert "cartao" in leitura.notes.lower()


def test_com_cartao_o_peso_entra_na_comanda(
    balanca_de_comanda, comanda, manager_user, api_client, account
):
    bind_command_to_scale(scale=balanca_de_comanda, reference=comanda.code, user=manager_user)

    response = api_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca_de_comanda.id), "weight_kg": "0.480", "is_stable": True},
        format="json",
    )
    assert response.status_code == 201

    with tenant_context(account):
        item = OrderItem.objects.get()
        assert item.command_id == comanda.pk
        assert item.order.order_type == Order.TYPE_COMMAND
        comanda.refresh_from_db()
        assert comanda.status == Command.STATUS_OCCUPIED


def test_a_nota_de_pesagem_imprime_o_numero_da_comanda(
    balanca_de_comanda, comanda, manager_user, api_client, account
):
    """É a única barreira que não depende de o operador lembrar de nada."""
    from apps.printers.models import PrintJob

    bind_command_to_scale(scale=balanca_de_comanda, reference=comanda.code, user=manager_user)
    api_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca_de_comanda.id), "weight_kg": "0.480", "is_stable": True},
        format="json",
    )

    with tenant_context(account):
        job = PrintJob.objects.get(job_type=PrintJob.TYPE_WEIGH)
    texto = job.payload["text_content"]
    assert f"COMANDA {comanda.number}" in texto
    assert "/kg" in texto
    assert job.payload["command"]["number"] == comanda.number


def test_a_segunda_pesagem_anota_de_novo_na_mesma_comanda(
    balanca_de_comanda, comanda, manager_user
):
    """Duas pesagens, duas anotações — e nenhum pedido.

    Antes, a primeira pesagem ABRIA um pedido para o cartão e a segunda o
    reusava. Era esse gesto que prendia a comanda a um pedido que talvez
    ninguém fosse pagar.
    """
    primeira = _leitura(balanca_de_comanda, "0.300")
    segunda = _leitura(balanca_de_comanda, "0.450")

    um = weigh_into_command(
        scale=balanca_de_comanda, command=comanda, user=manager_user, scale_reading=primeira
    )
    dois = weigh_into_command(
        scale=balanca_de_comanda, command=comanda, user=manager_user, scale_reading=segunda
    )

    assert um.pk != dois.pk
    assert um.command_id == dois.command_id == comanda.pk
    with tenant_context(comanda.account):
        assert Order.objects.filter(command=comanda).count() == 0


def test_a_mesma_pesagem_nao_e_lancada_duas_vezes(
    balanca_de_comanda, comanda, manager_user
):
    """A leitura fica CONSUMIDA: o cliente não paga duas vezes pelo corte."""
    leitura = _leitura(balanca_de_comanda, "0.300")
    weigh_into_command(
        scale=balanca_de_comanda, command=comanda, user=manager_user, scale_reading=leitura
    )
    leitura.refresh_from_db()

    with pytest.raises(ValidationError):
        weigh_into_command(
            scale=balanca_de_comanda, command=comanda, user=manager_user, scale_reading=leitura
        )



def test_o_modo_balcao_continua_criando_pedido_avulso(
    balanca_de_comanda, manager_user, api_client, account
):
    """A balança de balcão não muda de comportamento."""
    balanca_de_comanda.weighing_mode = Scale.MODE_COUNTER
    balanca_de_comanda.save(update_fields=["weighing_mode"])

    response = api_client.post(
        "/api/v1/scales/readings/",
        {"scale": str(balanca_de_comanda.id), "weight_kg": "0.480", "is_stable": True},
        format="json",
    )
    assert response.status_code == 201
    with tenant_context(account):
        assert Order.objects.filter(order_type=Order.TYPE_COUNTER).exists()
