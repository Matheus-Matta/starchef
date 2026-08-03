from decimal import Decimal

import pytest
from rest_framework_simplejwt.tokens import AccessToken

from apps.menu.models import Product
from apps.orders.models import Order
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading


@pytest.mark.django_db
def test_automatic_scale_creates_pending_counter_order_item_and_print_job(
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
    product.pricing_unit = Product.PRICING_KG
    product.sale_price = Decimal("79.90")
    product.save(update_fields=["pricing_unit", "sale_price", "updated_at"])
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Etiqueta balanca",
        endpoint="Teste",
        auto_print=True,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca buffet",
        port="COM2",
        product=product,
        printer=printer,
        auto_print=True,
    )
    claim = api_client.post(
        f"/api/v1/scales/{scale.id}/claim-agent/",
        {"instance_id": "pdv-caixa-1"},
        format="json",
    )
    assert claim.status_code == 200, claim.data

    response = api_client.post(
        "/api/v1/scales/readings/",
        {
            "scale": str(scale.id),
            "agent_instance_id": "pdv-caixa-1",
            "weight_kg": "0.750",
            "tare_kg": "0.000",
            "is_stable": True,
            "source": "agent",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    reading = ScaleReading.all_objects.get(pk=response.data["id"])
    assert reading.order_item is not None
    order = reading.order_item.order
    assert order.order_type == Order.TYPE_COUNTER
    assert order.status == Order.STATUS_AWAITING_PAYMENT
    assert order.payment_status == Order.PAYMENT_PENDING
    assert reading.order_item.quantity == Decimal("0.750")
    assert PrintJob.all_objects.filter(
        order=order,
        printer=printer,
        job_type=PrintJob.TYPE_WEIGH,
        status=PrintJob.STATUS_PENDING,
    ).exists()


@pytest.mark.django_db
def test_automatic_scale_reading_succeeds_without_agent_claim(
    api_client,
    manager_user,
    account,
    restaurant,
    branch,
    product,
):
    # O PDV lê a balança direto pela porta serial (SerialScaleReader) e nunca
    # chama claim-agent nem manda agent_instance_id — a exclusividade é local
    # (SO + trava de arquivo), não um lease no servidor. Uma balança com
    # auto_print precisa aceitar a leitura mesmo sem reserva nenhuma, senão
    # nenhum fechamento automático de comanda funciona.
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    product.pricing_unit = Product.PRICING_KG
    product.sale_price = Decimal("79.90")
    product.save(update_fields=["pricing_unit", "sale_price", "updated_at"])
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Etiqueta balanca",
        endpoint="Teste",
        auto_print=True,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca buffet",
        port="COM2",
        product=product,
        printer=printer,
        auto_print=True,
    )

    response = api_client.post(
        "/api/v1/scales/readings/",
        {
            "scale": str(scale.id),
            "weight_kg": "0.750",
            "tare_kg": "0.000",
            "is_stable": True,
            "source": "agent",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    reading = ScaleReading.all_objects.get(pk=response.data["id"])
    assert reading.order_item is not None


@pytest.mark.django_db
def test_automatic_scale_rejects_second_pdv_while_lease_is_active(
    api_client,
    manager_user,
    account,
    restaurant,
    branch,
):
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}"
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca exclusiva",
        port="COM2",
        auto_print=True,
    )

    first = api_client.post(
        f"/api/v1/scales/{scale.id}/claim-agent/",
        {"instance_id": "pdv-1"},
        format="json",
    )
    second = api_client.post(
        f"/api/v1/scales/{scale.id}/claim-agent/",
        {"instance_id": "pdv-2"},
        format="json",
    )

    assert first.status_code == 200
    assert first.data["claimed"] is True
    assert second.status_code == 409
    assert second.data["claimed"] is False


@pytest.mark.django_db
def test_non_automatic_scale_only_records_reading(
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
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca manual",
        port="COM3",
        product=product,
        auto_print=False,
    )

    response = api_client.post(
        "/api/v1/scales/readings/",
        {
            "scale": str(scale.id),
            "weight_kg": "1.000",
            "is_stable": True,
            "source": "agent",
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Order.all_objects.count() == 0
    assert PrintJob.all_objects.count() == 0
