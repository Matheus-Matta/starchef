import uuid

import pytest

from apps.orders.models import Order, OrderBatch, OrderItem
from apps.orders.services import (
    add_order_item,
    create_order,
    send_order_to_kitchen,
    update_order_item_status,
)
from apps.printers.models import Printer, PrintJob


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
    assert "RODADA" not in first_job.payload["text_content"]
    assert "TIPO" not in first_job.payload["text_content"]
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
