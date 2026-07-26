import pytest

from apps.orders.models import Order, OrderItem
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
