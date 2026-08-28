from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from rest_framework_simplejwt.tokens import AccessToken

from apps.customers.models import Customer, CustomerAddress
from apps.menu.models import ProductAddon, ProductVariation
from apps.orders.models import Order
from apps.orders.services import add_order_item, create_order
from apps.printers.models import Printer, PrintJob
from apps.printers.services import _order_context_lines, register_print_job
from apps.restaurants.models import TableSector


@pytest.mark.django_db
def test_customer_receipt_uses_selected_printer_and_manual_flag(
    api_client,
    manager_user,
    account,
    restaurant,
    branch,
    product,
):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
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
    # O agente local do PDV le o texto pronto direto desta resposta (nao
    # busca o PrintJob de novo); sem "payload" aqui ele caia pro conversor
    # generico de HTML, que gruda rotulo e valor ("SubtotalR$ 237,00").
    assert response.data["payload"]["text_content"]
    assert product.name in response.data["payload"]["text_content"]
    job = PrintJob.all_objects.get(pk=response.data["print_job_id"])
    assert job.payload["manual_only"] is True
    assert job.payload["text_content"]
    assert product.name in job.payload["text_content"]
    text = job.payload["text_content"]
    assert f"Pedido nº {order.sequence}" in text
    assert "RECIBO DE VENDA - NAO E DOCUMENTO FISCAL" in text
    assert "BALCAO" in text
    product_line = next(line for line in text.splitlines() if product.name in line)
    assert len(product_line) == 42
    assert product_line.endswith("R$ 50.00")


@pytest.mark.django_db
def test_receipt_detalha_variacao_no_produto_e_adicional_com_valor(
    account, restaurant, branch, manager_user, product
):
    """O recibo nao mostrava variacao nem adicional — so o nome do produto.

    O cliente pagava por um item composto e nao via a composicao. Agora a
    variacao sai colada no produto e cada adicional vira uma linha indentada
    com o quanto acrescentou. O valor da linha do produto ja soma tudo, entao
    as linhas de adicional sao detalhamento, e o TOTAL nao muda.
    """
    variation = ProductVariation.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        product=product,
        name="Grande",
        price_delta=Decimal("3.00"),
    )
    addon = ProductAddon.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Bacon",
        price=Decimal("4.00"),
    )
    addon.products.add(product)
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
        variations=[str(variation.id)],
        addons=[str(addon.id)],
    )
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Caixa",
        endpoint="Impressora Caixa",
        is_active=True,
    )

    job = register_print_job(order=order, user=manager_user, printer=printer)

    text = job.payload["text_content"]
    product_line = next(line for line in text.splitlines() if product.name in line)
    assert f"{product.name} - Grande" in product_line
    # 2 x (25,00 base + 3,00 variacao + 4,00 adicional) = 64,00
    assert product_line.endswith("R$ 64.00")
    addon_line = next(line for line in text.splitlines() if "Bacon" in line)
    assert addon_line.startswith("  Bacon")
    assert addon_line.endswith("R$ 8.00")
    assert "2 x Bacon" not in text
    assert "R$ 64.00" in text
    assert f"{product.name} - Grande" in job.html_content


@pytest.mark.django_db
def test_printer_test_connection_job_is_manual_only(
    api_client, manager_user, account, restaurant, branch
):
    """A nota de teste não pode disparar sozinha pelo agente automático.

    Sem `manual_only=True` no payload, o job (status RENDERED, um dos que o
    LocalDeviceAgent varre automaticamente) saía impresso duas vezes: uma
    pela tela de teste (que imprime e confirma na hora) e outra pelo mesmo
    agente reagindo ao evento de tempo real desta MESMA criação.
    """
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")
    # `test-connection` exige `CanUseOrManageDevices`; um manager comum não
    # tem `devices.manage` por padrão.
    manager_user.profile.profile_type = "owner"
    manager_user.profile.branch = None
    manager_user.profile.save(update_fields=["profile_type", "branch", "updated_at"])
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Caixa",
        endpoint="Impressora Caixa",
        is_active=True,
    )

    response = api_client.post(f"/api/v1/printers/{printer.id}/test-connection/")

    assert response.status_code == 201, response.data
    assert response.data["payload"]["manual_only"] is True
    job = PrintJob.all_objects.get(pk=response.data["print_job_id"])
    assert job.payload["manual_only"] is True
    assert job.status == PrintJob.STATUS_RENDERED


@pytest.mark.django_db
def test_receipt_header_matches_table_and_command(account, restaurant, branch, table, command, manager_user):
    command.current_table = table
    command.save(update_fields=["current_table", "updated_at"])
    order = create_order(
        restaurant=restaurant,
        order_type=Order.TYPE_COMMAND,
        user=manager_user,
        command=command,
    )
    assert _order_context_lines(order) == [f"Mesa: {table.number} - Comanda: {command.code}"]


@pytest.mark.django_db
def test_receipt_header_matches_counter_with_customer(account, restaurant, branch, manager_user):
    customer = Customer.objects.create(account=account, restaurant=restaurant, branch=branch, name="Joana", phone="11999990000")
    order = create_order(
        restaurant=restaurant,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
        customer=customer,
    )
    assert _order_context_lines(order) == ["BALCAO", "Cliente: Joana"]


@pytest.mark.django_db
def test_receipt_header_matches_delivery_with_address(account, restaurant, branch, manager_user):
    customer = Customer.objects.create(account=account, restaurant=restaurant, branch=branch, name="Joana", phone="11999990000")
    address = CustomerAddress.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        customer=customer,
        street="Rua das Flores",
        number="123",
        district="Centro",
        city="Sao Paulo",
        state="SP",
    )
    order = create_order(
        restaurant=restaurant,
        order_type=Order.TYPE_DELIVERY,
        user=manager_user,
        customer=customer,
        delivery_address=address,
    )
    assert _order_context_lines(order) == [
        "DELIVERY",
        "Cliente: Joana",
        "Telefone: 11999990000",
        "Rua das Flores, 123",
        "Centro - Sao Paulo/SP",
    ]


@pytest.mark.django_db
def test_automatic_receipt_uses_the_only_active_sector_printer(account, restaurant, branch, manager_user, product):
    sector = TableSector.objects.create(account=account, restaurant=restaurant, branch=branch, name="Cozinha")
    printer = Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        name="Cozinha",
        endpoint="Impressora Cozinha",
        sector=sector,
        is_active=True,
        auto_print=True,
    )
    order = create_order(restaurant=restaurant, order_type=Order.TYPE_COUNTER, user=manager_user)
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    job = register_print_job(order=order, user=manager_user, job_type=PrintJob.TYPE_RECEIPT)

    assert job.printer == printer


@pytest.mark.django_db
def test_automatic_receipt_rejects_ambiguous_sector_printers(
    account, restaurant, branch, manager_user, product
):
    for name in ("Cozinha", "Bar"):
        sector = TableSector.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            name=name,
        )
        Printer.objects.create(
            account=account,
            restaurant=restaurant,
            branch=branch,
            name=name,
            endpoint=f"Impressora {name}",
            sector=sector,
            is_active=True,
            auto_print=True,
        )
    order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    add_order_item(order=order, product=product, quantity=1, user=manager_user)

    with pytest.raises(ValidationError, match="mais de uma impressora setorizada"):
        register_print_job(
            order=order,
            user=manager_user,
            job_type=PrintJob.TYPE_RECEIPT,
        )

    assert not PrintJob.objects.filter(order=order).exists()
