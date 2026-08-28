from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.core.models import AuditLog
from apps.orders.models import Order, OrderBatch, OrderItem
from apps.orders.services import (
    add_order_item,
    create_order,
    send_order_to_kitchen,
    void_order_item,
)
from apps.payments.models import CashStation
from apps.payments.services import open_cash_register
from apps.printers.models import Printer, PrintJob
from apps.restaurants.models import Restaurant, Table

pytestmark = pytest.mark.django_db


def _printer_for_product(account, restaurant, branch, product, table):
    product.sector = table.sector
    product.save(update_fields=["sector", "updated_at"])
    return Printer.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        sector=table.sector,
        name="Cozinha",
        endpoint="TEST",
        auto_print=True,
    )


def test_waiter_login_rejects_pdv_profile_and_accepts_waiter(api_client, manager_user, waiter_user):
    denied = api_client.post(
        "/api/v1/auth/login/",
        {"username": manager_user.username, "password": "secret123", "client": "waiter_app"},
        format="json",
    )
    assert denied.status_code == 401
    assert "perfil de garçom" in str(denied.data)

    accepted = api_client.post(
        "/api/v1/auth/login/",
        {"username": waiter_user.username, "password": "secret123", "client": "waiter_app"},
        format="json",
    )
    assert accepted.status_code == 200
    assert accepted.data["user"]["profile_type"] == "waiter"


def test_create_with_item_never_leaves_an_empty_order(api_client, manager_user, restaurant, product):
    api_client.force_authenticate(user=None)
    # The shared client is anonymous in this test module; authenticate through
    # the normal login so the tenant middleware receives the same JWT as apps.
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123", "no_cookie": True},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    invalid = api_client.post(
        "/api/v1/orders/create-with-item/",
        {"order_type": "counter"},
        format="json",
    )
    assert invalid.status_code == 400
    assert Order.all_objects.count() == 0

    created = api_client.post(
        "/api/v1/orders/create-with-item/",
        {
            "order_type": "counter",
            "item": {"product": str(product.id), "quantity": 1},
        },
        format="json",
    )
    assert created.status_code == 201, created.data
    assert Order.all_objects.count() == 1
    assert OrderItem.all_objects.filter(order_id=created.data["id"]).count() == 1


def test_create_with_item_on_open_command_appends_instead_of_conflicting(
    api_client,
    manager_user,
    restaurant,
    command,
    product,
):
    """A comanda ja aberta recebe o item, em vez de recusar o lancamento.

    O app do garcom lanca offline. Quando a operacao enfileirada sobe, a
    comanda quase sempre ja foi aberta por alguem — o proprio garcom em outro
    aparelho, o caixa, ou a mesma operacao por outro caminho. Respondendo 409,
    o item virava pendencia bloqueada e sumia do pedido.
    """
    api_client.force_authenticate(user=None)
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123", "no_cookie": True},
        format="json",
    )
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    payload = {
        "order_type": "command",
        "command": str(command.id),
        "item": {"product": str(product.id), "quantity": 1},
    }
    created = api_client.post("/api/v1/orders/create-with-item/", payload, format="json")
    assert created.status_code == 201, created.data

    again = api_client.post("/api/v1/orders/create-with-item/", payload, format="json")

    assert again.status_code == 200, again.data
    # O mesmo pedido, agora com os dois itens: nenhum pedido novo foi aberto.
    assert again.data["id"] == created.data["id"]
    assert Order.all_objects.filter(command=command).count() == 1
    itens = OrderItem.all_objects.filter(order_id=created.data["id"])
    # Item identico soma na linha que ja existe, como em qualquer lancamento
    # repetido — o que importa aqui e que a quantidade nao se perdeu.
    assert itens.count() == 1
    assert itens.first().quantity == Decimal("2")


def test_immediate_kitchen_dispatch_prints_linked_cancellation(
    account,
    restaurant,
    branch,
    manager_user,
    product,
    table,
):
    _printer_for_product(account, restaurant, branch, product, table)
    order = create_order(restaurant=restaurant, order_type=Order.TYPE_COUNTER, user=manager_user)
    item = add_order_item(order=order, product=product, quantity=1, user=manager_user)

    send_order_to_kitchen(order, manager_user)
    item.refresh_from_db()
    original = PrintJob.objects.get(
        order=order,
        job_type=PrintJob.TYPE_KITCHEN,
        status=PrintJob.STATUS_RENDERED,
    )
    assert item.status == OrderItem.STATUS_SENT
    assert item.batch.status == OrderBatch.STATUS_SENT

    void_order_item(item, manager_user, "Cliente desistiu depois do envio")
    cancellation = PrintJob.objects.get(
        original_job=original,
        cancelled_item=item,
        job_type=PrintJob.TYPE_KITCHEN_CANCEL,
    )
    assert cancellation.status == PrintJob.STATUS_RENDERED
    assert cancellation.payload["original_print_serial"] == str(original.serial)
    assert str(original.serial) in cancellation.payload["text_content"]
    audit = AuditLog.all_objects.filter(entity="OrderItem", object_id=str(item.id)).first()
    assert audit.metadata["within_print_grace_period"] is False


def test_pdv_and_waiter_app_dispatch_immediately(
    api_client,
    account,
    restaurant,
    branch,
    manager_user,
    waiter_user,
    product,
    table,
):
    _printer_for_product(account, restaurant, branch, product, table)

    pdv_order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=manager_user,
    )
    pdv_item = add_order_item(
        order=pdv_order,
        product=product,
        quantity=1,
        user=manager_user,
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(manager_user).access_token}"
    )

    pdv_response = api_client.post(
        f"/api/v1/orders/{pdv_order.id}/send-to-kitchen/",
        {},
        format="json",
    )

    assert pdv_response.status_code == 200, pdv_response.data
    pdv_item.refresh_from_db()
    pdv_job = PrintJob.all_objects.get(order=pdv_order)
    assert pdv_item.status == OrderItem.STATUS_SENT
    assert pdv_item.batch.status == OrderBatch.STATUS_SENT
    assert pdv_job.status == PrintJob.STATUS_RENDERED
    assert pdv_job.available_at <= timezone.now()

    waiter_order = create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=waiter_user,
    )
    waiter_item = add_order_item(
        order=waiter_order,
        product=product,
        quantity=1,
        user=waiter_user,
    )
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(waiter_user).access_token}"
    )

    waiter_response = api_client.post(
        f"/api/v1/orders/{waiter_order.id}/send-to-kitchen/",
        {},
        format="json",
    )

    assert waiter_response.status_code == 200, waiter_response.data
    waiter_item.refresh_from_db()
    waiter_job = PrintJob.all_objects.get(order=waiter_order)
    assert waiter_item.status == OrderItem.STATUS_SENT
    assert waiter_item.batch.status == OrderBatch.STATUS_SENT
    assert waiter_job.status == PrintJob.STATUS_RENDERED
    assert waiter_job.available_at <= timezone.now()


def test_table_api_derives_occupied_status_from_linked_command(api_client, manager_user, table, command):
    command.current_table = table
    command.save(update_fields=["current_table", "updated_at"])
    Table.objects.filter(pk=table.pk).update(status=Table.STATUS_FREE)

    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(manager_user).access_token}")
    response = api_client.get("/api/v1/tables/", {"restaurant": str(table.restaurant_id)})
    assert response.status_code == 200
    row = next(item for item in response.data["results"] if item["id"] == str(table.id))
    assert row["status"] == Table.STATUS_OCCUPIED


def test_assigned_operator_resumes_open_cash_session(
    account,
    restaurant,
    branch,
    manager_user,
    waiter_user,
):
    station = CashStation.objects.create(
        account=account,
        restaurant=restaurant,
        name="PDV 1",
        code="PDV1",
    )
    station.operators.add(manager_user, waiter_user)
    opened = open_cash_register(
        restaurant=restaurant,
        cash_station=station,
        user=manager_user,
        opening_amount=Decimal("50.00"),
    )

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(waiter_user).access_token}")
    response = client.get("/api/v1/cash-register/current/")
    assert response.status_code == 200, response.content
    assert response.json()["id"] == str(opened.id)


def test_current_cash_register_does_not_leak_across_restaurants(
    account,
    restaurant,
    manager_user,
):
    """O caixa e' fisico e pertence a uma unica unidade: trocar de restaurante
    no PDV sem um caixa aberto la' precisa bloquear a tela, nao herdar o caixa
    aberto em outro restaurante do mesmo operador/conta."""
    other_restaurant = Restaurant.objects.create(
        account=account,
        legal_name="Outra Unidade LTDA",
        trade_name="Outra Unidade",
        cnpj="11.111.111/0001-11",
    )
    station = CashStation.objects.create(
        account=account,
        restaurant=restaurant,
        name="PDV 1",
        code="PDV1",
    )
    station.operators.add(manager_user)
    opened = open_cash_register(
        restaurant=restaurant,
        cash_station=station,
        user=manager_user,
        opening_amount=Decimal("50.00"),
    )

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(manager_user).access_token}")

    same_restaurant = client.get("/api/v1/cash-register/current/", {"restaurant": str(restaurant.id)})
    assert same_restaurant.status_code == 200, same_restaurant.content
    assert same_restaurant.json()["id"] == str(opened.id)

    other = client.get("/api/v1/cash-register/current/", {"restaurant": str(other_restaurant.id)})
    assert other.status_code == 404, other.content
