import uuid
from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order, OrderBatch, OrderItem
from apps.orders.services import (
    add_order_item,
    create_order,
    send_order_to_kitchen,
    update_order_item_status,
)
from apps.printers.models import Printer, PrintJob
from apps.restaurants.models import TableSector


@pytest.mark.django_db
def test_kitchen_agrupa_por_setor_e_envia_a_cada_impressora_do_setor(
    account, restaurant, branch, table, category, product, manager_user
):
    """Dois itens da cozinha saem num cupom so; o do bar sai separado.

    Cada setor imprime em TODAS as suas impressoras ativas, escolhidas pelo
    id do setor (o nome e so referencia).
    """
    cozinha = table.sector
    bar = TableSector.objects.create(
        account=account, restaurant=restaurant, branch=branch, name="Bar"
    )
    product.sector = cozinha
    product.save(update_fields=["sector", "updated_at"])
    coca = Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        category=category,
        sector=bar,
        name="Coca-Cola",
        internal_code="COCA",
        sale_price=Decimal("7.00"),
    )
    # Duas impressoras no MESMO setor: o cupom da cozinha sai nas duas.
    for nome in ("Cozinha 1", "Cozinha 2"):
        Printer.objects.create(
            account=account, restaurant=restaurant, branch=branch,
            sector=cozinha, name=nome, endpoint="T", auto_print=True,
        )
    Printer.objects.create(
        account=account, restaurant=restaurant, branch=branch,
        sector=bar, name="Bar 1", endpoint="T", auto_print=True,
    )

    order = create_order(
        restaurant=restaurant, branch=branch, order_type=Order.TYPE_TABLE,
        table=table, user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=2, user=manager_user)
    add_order_item(order=order, product=coca, quantity=1, user=manager_user)

    send_order_to_kitchen(order, manager_user)

    jobs = list(PrintJob.objects.filter(order=order))
    por_impressora = {job.printer.name: job.payload["text_content"] for job in jobs}

    # Um cupom por impressora: duas da cozinha + uma do bar.
    assert sorted(por_impressora) == ["Bar 1", "Cozinha 1", "Cozinha 2"]
    # As duas impressoras da cozinha recebem o MESMO cupom, com o item da
    # cozinha e sem o do bar.
    assert por_impressora["Cozinha 1"] == por_impressora["Cozinha 2"]
    assert "2x X-Burger" in por_impressora["Cozinha 1"]
    assert "Coca-Cola" not in por_impressora["Cozinha 1"]
    # E o bar recebe so o que e dele.
    assert "1x Coca-Cola" in por_impressora["Bar 1"]
    assert "X-Burger" not in por_impressora["Bar 1"]


@pytest.mark.django_db
def test_kitchen_prints_only_new_batch_items_for_product_sector(
    account, restaurant, branch, table, product, manager_user
):
    product.sector = table.sector
    product.save(update_fields=["sector", "updated_at"])
    Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=table.sector,
        name="Cozinha",
        endpoint="Teste",
        auto_print=True,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    first_item = add_order_item(
        order=order,
        product=product,
        quantity=1,
        user=manager_user,
    )

    send_order_to_kitchen(order, manager_user)
    first_job = PrintJob.objects.get(order=order)
    assert first_job.payload["item_ids"] == [str(first_item.id)]
    assert "NOVO PEDIDO" in first_job.payload["text_content"]
    assert "MESA: 1" in first_job.payload["text_content"]
    assert "X-Burger" in first_job.payload["text_content"]
    # A comanda identifica de onde veio: pedido, rodada, setor e hora. Sem
    # isso a cozinha recebia so a lista de produtos, sem saber o pedido.
    assert f"PEDIDO #{order.sequence}" in first_job.payload["text_content"]
    assert "RODADA 1" in first_job.payload["text_content"]
    assert "SALAO" in first_job.payload["text_content"]
    assert "TOTAL DE ITENS" in first_job.payload["text_content"]
    # Mesa/comanda ja dizem que e do salao: repetir o tipo seria ruido.
    assert "TABLE" not in first_job.payload["text_content"]
    assert "NOVO PEDIDO" in first_job.html_content
    assert "Mesa: 1" in first_job.html_content
    first_item.refresh_from_db()

    update_order_item_status(
        first_item,
        OrderItem.STATUS_PREPARING,
        manager_user,
    )
    second_item = add_order_item(
        order=order,
        product=product,
        quantity=2,
        user=manager_user,
    )
    send_order_to_kitchen(order, manager_user)

    jobs = list(PrintJob.objects.filter(order=order).order_by("created_at"))
    assert len(jobs) == 2
    assert jobs[1].payload["batch_number"] == 2
    assert jobs[1].payload["item_ids"] == [str(second_item.id)]
    assert str(first_item.id) not in jobs[1].payload["item_ids"]
    assert "2x X-Burger" in jobs[1].payload["text_content"]
    assert "1x X-Burger" not in jobs[1].payload["text_content"]
    assert jobs[1].html_content.count("X-Burger") == 1


@pytest.mark.django_db
def test_kitchen_new_order_note_shows_command_and_table_when_present(
    account, restaurant, branch, table, command, product, manager_user
):
    product.sector = table.sector
    product.save(update_fields=["sector", "updated_at"])
    Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=table.sector,
        name="Cozinha",
        endpoint="Teste",
        auto_print=True,
    )
    command.current_table = table
    command.save(update_fields=["current_table", "updated_at"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COMMAND,
        command=command,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    send_order_to_kitchen(order, manager_user)

    job = PrintJob.objects.get(order=order)
    assert f"COMANDA: {command.code}" in job.payload["text_content"]
    assert "MESA: 1" in job.payload["text_content"]
    assert f"Comanda: {command.code}" in job.html_content
    assert "Mesa: 1" in job.html_content


@pytest.mark.django_db
def test_kitchen_offline_printed_reuses_client_serial_and_skips_reprint(
    account, restaurant, branch, table, product, manager_user
):
    """PDV sem internet já imprimiu a comanda localmente antes de sincronizar."""
    product.sector = table.sector
    product.save(update_fields=["sector", "updated_at"])
    Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=table.sector,
        name="Cozinha",
        endpoint="Teste",
        auto_print=True,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    client_serial = uuid.uuid4()
    send_order_to_kitchen(
        order,
        manager_user,
        client_batch_serial=str(client_serial),
        offline_printed=True,
    )

    batch = OrderBatch.objects.get(order=order)
    assert batch.serial == client_serial

    job = PrintJob.objects.get(order=order)
    assert job.status == PrintJob.STATUS_PRINTED
    assert job.printed_at is not None
    assert job.payload["offline_printed"] is True
    assert f"REF: {client_serial}" in job.payload["text_content"]


@pytest.mark.django_db
def test_kitchen_does_not_create_job_without_sector_printer(
    restaurant, branch, table, product, manager_user
):
    product.sector = table.sector
    product.save(update_fields=["sector", "updated_at"])
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_TABLE,
        table=table,
        user=manager_user,
    )
    add_order_item(
        order=order,
        product=product,
        quantity=1,
        user=manager_user,
    )

    send_order_to_kitchen(order, manager_user)

    assert not PrintJob.objects.filter(order=order).exists()
