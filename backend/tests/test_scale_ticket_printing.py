from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import Order, OrderItem
from apps.printers.models import Printer, PrintJob, Scale, ScaleReading
from apps.restaurants.models import Command


def _product(
    *,
    account,
    restaurant,
    branch,
    name,
    code,
    price,
    pricing_unit=Product.PRICING_UNIT,
):
    return Product.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name=name,
        internal_code=code,
        sale_price=price,
        pricing_unit=pricing_unit,
    )


@pytest.mark.django_db
def test_checkout_command_prints_complete_recalculated_ticket_with_code128(
    admin_client,
    account,
    restaurant,
    branch,
):
    weighed = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet por kg",
        code="BUFFET-KG",
        price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG,
    )
    drink = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Agua mineral",
        code="AGUA",
        price=Decimal("5.00"),
    )
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Termica da balanca",
        endpoint="Impressora Teste",
        is_active=True,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca buffet",
        product=weighed,
        printer=printer,
    )
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        scale=scale,
        weight_kg=Decimal("0.500"),
        is_stable=True,
    )
    command = Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=10,
    )

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": str(command.number),
            "scale_reading": str(reading.id),
            "extras": [{"product": str(drink.id), "quantity": 2}],
            "print": True,
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    assert Decimal(response.data["order"]["subtotal"]) == Decimal("39.95")
    assert Decimal(response.data["order"]["total"]) == Decimal("39.95")

    job = PrintJob.all_objects.get(pk=response.data["print_job"]["id"])
    assert job.printer_id == printer.id
    assert job.status == PrintJob.STATUS_PENDING
    assert job.payload["restaurant"] == {
        "id": str(restaurant.id),
        "trade_name": restaurant.trade_name,
        "legal_name": restaurant.legal_name,
        "cnpj": restaurant.cnpj,
    }
    assert job.payload["order"]["id"] == response.data["order"]["id"]
    assert job.payload["order"]["sequence"] == response.data["order"]["sequence"]
    assert job.payload["order"]["command"] == {
        "id": str(command.id),
        "number": command.number,
        "code": command.code,
    }
    assert [item["name"] for item in job.payload["items"]] == [
        weighed.name,
        drink.name,
    ]
    assert job.payload["subtotal"] == "39.95"
    assert job.payload["order_total"] == "39.95"
    assert job.payload["order"]["total"] == "39.95"
    # `total` continua sendo o total legado do item pesado.
    assert job.payload["total"] == "29.95"
    assert job.payload["barcode"]["symbology"] == "CODE128"
    assert job.payload["barcode"]["value"] == command.code

    for expected in (restaurant.trade_name, weighed.name, drink.name):
        assert expected in job.payload["text_content"]
        assert expected in job.html_content
    assert "39.95" in job.payload["text_content"]
    text_lines = job.payload["text_content"].splitlines()
    weighed_line = next(line for line in text_lines if weighed.name in line)
    drink_line = next(line for line in text_lines if drink.name in line)
    assert len(weighed_line) == 42
    assert weighed_line.endswith("R$ 29.95")
    assert len(drink_line) == 42
    assert drink_line.endswith("R$ 10.00")
    assert "39,95" in job.html_content
    assert f"{weighed.name}</span><span>R$ 29,95" in job.html_content
    assert "CODE128" in job.payload["text_content"]
    assert 'data-symbology="CODE128"' in job.html_content
    assert "data:image/png;base64," in job.html_content
    assert command.code in job.html_content


@pytest.mark.django_db
def test_checkout_command_does_not_guess_default_printer_and_rolls_back(
    admin_client,
    account,
    restaurant,
    branch,
):
    weighed = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet por kg",
        code="BUFFET-KG",
        price=Decimal("50.00"),
        pricing_unit=Product.PRICING_KG,
    )
    extra = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Suco",
        code="SUCO",
        price=Decimal("8.00"),
    )
    # Ativa e no mesmo restaurante, mas nao ha campo/constraint que a marque
    # como padrao. O backend nao pode escolhe-la apenas por ordenacao.
    Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Caixa",
        endpoint="Impressora Caixa",
        is_active=True,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca sem impressora",
        product=weighed,
        printer=None,
    )
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        scale=scale,
        weight_kg=Decimal("1.000"),
        is_stable=True,
    )
    command = Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=11,
    )

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": command.code,
            "scale_reading": str(reading.id),
            "extras": [{"product": str(extra.id), "quantity": 1}],
            "print": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "impressora padrao segura" in str(response.data["detail"]).lower()
    assert not Order.all_objects.exists()
    assert not OrderItem.all_objects.exists()
    assert not PrintJob.all_objects.exists()
    reading.refresh_from_db()
    command.refresh_from_db()
    assert reading.order_item_id is None
    assert command.current_order_id is None
    assert command.status == Command.STATUS_FREE


@pytest.mark.django_db
def test_weigh_endpoint_does_not_consume_reading_with_inactive_printer(
    admin_client,
    account,
    restaurant,
    branch,
):
    weighed = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet por kg",
        code="BUFFET-KG",
        price=Decimal("50.00"),
        pricing_unit=Product.PRICING_KG,
    )
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Termica inativa",
        endpoint="Impressora Teste",
        is_active=False,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca",
        product=weighed,
        printer=printer,
    )
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        scale=scale,
        weight_kg=Decimal("0.750"),
        is_stable=True,
    )
    order = Order.objects.create(
        account=account,
        restaurant=restaurant,
        branch=None,
        sequence=1,
        order_type=Order.TYPE_COUNTER,
    )

    response = admin_client.post(
        f"/api/v1/scales/{scale.id}/weigh/",
        {
            "order": str(order.id),
            "scale_reading": str(reading.id),
            "print": True,
        },
        format="json",
    )

    assert response.status_code == 400
    assert "inativa" in str(response.data["detail"]).lower()
    assert not OrderItem.all_objects.exists()
    assert not PrintJob.all_objects.exists()
    reading.refresh_from_db()
    assert reading.order_item_id is None


def _weigh_ticket_setup(account, restaurant, branch):
    """Monta balanca, impressora, leitura e comanda prontas para o checkout."""
    weighed = _product(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Buffet por kg",
        code="BUFFET-KG",
        price=Decimal("59.90"),
        pricing_unit=Product.PRICING_KG,
    )
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Termica da balanca",
        endpoint="Impressora Teste",
        is_active=True,
    )
    scale = Scale.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Balanca buffet",
        product=weighed,
        printer=printer,
    )
    reading = ScaleReading.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        scale=scale,
        weight_kg=Decimal("0.500"),
        is_stable=True,
    )
    command = Command.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        number=77,
    )
    return scale, reading, command


@pytest.mark.django_db
def test_requeue_reprints_the_same_ticket_without_touching_the_order(
    admin_client,
    account,
    restaurant,
    branch,
):
    scale, reading, command = _weigh_ticket_setup(account, restaurant, branch)
    checkout = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": str(command.number),
            "scale_reading": str(reading.id),
            "print": True,
        },
        format="json",
    )
    assert checkout.status_code == 201, checkout.data
    job_id = checkout.data["print_job"]["id"]
    order_id = checkout.data["order"]["id"]
    original = PrintJob.all_objects.get(pk=job_id)
    original_html = original.html_content
    original_payload = original.payload

    # Uma falha da impressora nao pode apagar a venda; o cupom fica repetivel.
    admin_client.post(f"/api/v1/print-jobs/{job_id}/mark-failed/", {"error": "sem papel"}, format="json")

    response = admin_client.post(f"/api/v1/print-jobs/{job_id}/requeue/", {}, format="json")

    assert response.status_code == 200, response.data
    job = PrintJob.all_objects.get(pk=job_id)
    assert job.status == PrintJob.STATUS_RENDERED
    assert job.error_message == ""
    assert job.printed_at is None
    # O conteudo original e preservado, incluindo o Code 128 da comanda.
    assert job.html_content == original_html
    assert job.payload == original_payload
    assert job.payload["barcode"]["value"] == command.code
    # Nenhum pedido ou item novo foi criado.
    assert PrintJob.all_objects.count() == 1
    assert Order.all_objects.count() == 1
    assert str(Order.all_objects.get().id) == order_id
    assert OrderItem.all_objects.count() == 1


@pytest.mark.django_db
def test_requeue_recusa_cupom_que_ainda_esta_na_fila(
    admin_client,
    account,
    restaurant,
    branch,
):
    scale, reading, command = _weigh_ticket_setup(account, restaurant, branch)
    checkout = admin_client.post(
        f"/api/v1/scales/{scale.id}/checkout-command/",
        {
            "command_code": str(command.number),
            "scale_reading": str(reading.id),
            "print": True,
        },
        format="json",
    )
    job_id = checkout.data["print_job"]["id"]
    assert PrintJob.all_objects.get(pk=job_id).status == PrintJob.STATUS_PENDING

    response = admin_client.post(f"/api/v1/print-jobs/{job_id}/requeue/", {}, format="json")

    # Reenfileirar aqui produziria uma segunda impressao silenciosa.
    assert response.status_code == 409
    assert PrintJob.all_objects.get(pk=job_id).status == PrintJob.STATUS_PENDING
