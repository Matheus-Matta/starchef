from datetime import timedelta
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
    dispatch_due_kitchen_batches,
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


def test_kitchen_grace_cancels_silently_then_prints_linked_cancellation(
    account,
    restaurant,
    branch,
    manager_user,
    product,
    table,
):
    _printer_for_product(account, restaurant, branch, product, table)
    order = create_order(restaurant=restaurant, order_type=Order.TYPE_COUNTER, user=manager_user)
    first = add_order_item(order=order, product=product, quantity=1, user=manager_user)

    send_order_to_kitchen(order, manager_user)
    first.refresh_from_db()
    first_batch = first.batch
    assert first.status == OrderItem.STATUS_QUEUED
    assert first_batch.status == OrderBatch.STATUS_SCHEDULED
    assert first_batch.dispatch_at > timezone.now()
    assert PrintJob.objects.filter(order=order, status=PrintJob.STATUS_SCHEDULED).count() == 1

    void_order_item(first, manager_user, "Cliente corrigiu antes da impressão")
    assert not PrintJob.objects.filter(order=order, job_type=PrintJob.TYPE_KITCHEN_CANCEL).exists()
    audit = AuditLog.all_objects.filter(entity="OrderItem", object_id=str(first.id)).first()
    assert audit.metadata["within_print_grace_period"] is True

    second = add_order_item(order=order, product=product, quantity=2, user=manager_user)
    send_order_to_kitchen(order, manager_user)
    second.refresh_from_db()
    second.batch.dispatch_at = timezone.now() - timedelta(seconds=1)
    second.batch.save(update_fields=["dispatch_at", "updated_at"])

    assert dispatch_due_kitchen_batches(account_id=account.id) == 1
    second.refresh_from_db()
    original = PrintJob.objects.get(
        order=order,
        job_type=PrintJob.TYPE_KITCHEN,
        status=PrintJob.STATUS_RENDERED,
    )
    assert second.status == OrderItem.STATUS_SENT

    void_order_item(second, manager_user, "Cliente desistiu depois do envio")
    cancellation = PrintJob.objects.get(
        original_job=original,
        cancelled_item=second,
        job_type=PrintJob.TYPE_KITCHEN_CANCEL,
    )
    assert cancellation.status == PrintJob.STATUS_RENDERED
    assert cancellation.payload["original_print_serial"] == str(original.serial)
    assert str(original.serial) in cancellation.payload["text_content"]


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
