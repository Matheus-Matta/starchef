import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.printers.models import Printer, PrintJob


@pytest.mark.django_db
def test_customer_receipt_uses_selected_printer_and_manual_flag(
    api_client,
    manager_user,
    account,
    restaurant,
    branch,
    product,
):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    manager_user.profile.branch = None
    manager_user.profile.save(update_fields=["branch", "updated_at"])
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Caixa",
        endpoint="Impressora Caixa",
        is_active=True,
    )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(
        order=order,
        product=product,
        quantity=2,
        user=manager_user,
    )

    response = api_client.post(
        f"/api/v1/orders/{order.id}/print/",
        {
            "job_type": "receipt",
            "printer": str(printer.id),
            "manual_only": True,
        },
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data["printer"]["id"] == str(printer.id)
    job = PrintJob.all_objects.get(pk=response.data["print_job_id"])
    assert job.payload["manual_only"] is True
    assert job.payload["text_content"]
    assert product.name in job.payload["text_content"]
    assert f"PEDIDO #{order.sequence}" in job.payload["text_content"]
