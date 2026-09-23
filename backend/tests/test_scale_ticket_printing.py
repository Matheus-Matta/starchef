from decimal import Decimal

import pytest

from apps.menu.models import Product
from apps.orders.models import CommandItem, Order, OrderItem
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
def test_checkout_command_lanca_anotacoes_pendentes_e_imprime_a_etiqueta(
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

    # O PRATO E A BEBIDA VIRAM ANOTACOES DA COMANDA, e nao itens de um pedido.
    # A balanca nao abre conta: quem monta o pedido e o caixa, com as anotacoes
    # pendentes dos cartoes que vao ser pagos juntos.
    assert not Order.all_objects.exists()
    assert not OrderItem.all_objects.exists()

    anotacoes = CommandItem.all_objects.filter(command=command).order_by("launched_at")
    assert [item.product_id for item in anotacoes] == [weighed.pk, drink.pk]
    assert all(
        item.command_status == CommandItem.STATUS_PENDENTE for item in anotacoes
    )
    assert anotacoes[0].quantity == Decimal("0.500")
    assert anotacoes[0].total_price == Decimal("29.95")
    assert anotacoes[1].quantity == 2
    assert anotacoes[1].total_price == Decimal("10.00")

    # O cartao fica em uso porque tem anotacao pendente — nao por causa de um
    # pedido preso a ele.
    command.refresh_from_db()
    assert command.current_order_id is None
    assert response.data["command"]["status"] == command.status
    assert response.data["weighed_item"]["command_status"] == CommandItem.STATUS_PENDENTE
    assert len(response.data["extra_items"]) == 1

    # A leitura fica consumida: a mesma pesagem nao vira uma segunda anotacao.
    reading.refresh_from_db()
    assert reading.command_item_id == anotacoes[0].pk
    assert reading.order_item_id is None

    # A ETIQUETA e o papel que o cliente leva ao caixa. Ela nao e o cupom do
    # pedido: nao ha pedido para resumir, e montar um so para imprimir seria o
    # gesto que este modelo existe para eliminar.
    job = PrintJob.all_objects.get(pk=response.data["print_job"]["id"])
    assert job.printer_id == printer.id
    assert job.status == PrintJob.STATUS_PENDING
    assert job.payload["command"] == str(command.id)
    assert job.payload["command_number"] == command.number
    assert job.payload["item"] == str(anotacoes[0].pk)
    texto = job.payload["text_content"]
    assert f"COMANDA {command.number}" in texto
    assert weighed.name in texto
    assert "29.95" in texto


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
def test_requeue_reimprime_a_mesma_etiqueta_sem_tocar_nas_anotacoes(
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
    item_id = checkout.data["weighed_item"]["id"]
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
    # O conteudo original e preservado: a etiqueta reimpressa e a MESMA.
    assert job.html_content == original_html
    assert job.payload == original_payload
    assert job.payload["command_number"] == command.number
    # Reimprimir e um gesto de papel, nao de dinheiro: nenhuma anotacao nova
    # entrou na comanda, e nenhum pedido nasceu.
    assert PrintJob.all_objects.count() == 1
    assert not Order.all_objects.exists()
    assert not OrderItem.all_objects.exists()
    assert CommandItem.all_objects.count() == 1
    assert str(CommandItem.all_objects.get().id) == item_id


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
