import pytest

from apps.invoices.models import Invoice
from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


@pytest.fixture
def account_with_financeiro(account):
    account.enabled_modules = ["financeiro"]
    account.save(update_fields=["enabled_modules"])
    return account


def make_order(restaurant, branch, user):
    return create_order(
        restaurant=restaurant,
        branch=branch,
        order_type=Order.TYPE_COUNTER,
        user=user,
    )


def make_invoice(order, *, status=Invoice.STATUS_PENDING, emission_type=Invoice.EMISSION_NORMAL):
    return Invoice.all_objects.create(
        account=order.account,
        restaurant=order.restaurant,
        branch=order.branch,
        order=order,
        status=status,
        emission_type=emission_type,
        number=str(order.sequence),
    )


def test_invoice_list_is_newest_first_and_includes_order_number(
    api_client, account_with_financeiro, restaurant, branch, manager_user
):
    """A retaguarda mostra a nota mais nova primeiro e identifica o pedido."""
    first = make_invoice(make_order(restaurant, branch, manager_user))
    second = make_invoice(make_order(restaurant, branch, manager_user))

    response = api_client.get("/api/v1/invoices/")

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"][:2]] == [str(second.pk), str(first.pk)]
    assert response.data["results"][0]["order_sequence"] == second.order.sequence


def test_invoice_list_filters_status_and_emission_type(
    api_client, account_with_financeiro, restaurant, branch, manager_user
):
    invoice = make_invoice(
        make_order(restaurant, branch, manager_user),
        emission_type=Invoice.EMISSION_CONTINGENCY,
    )
    make_invoice(make_order(restaurant, branch, manager_user), status=Invoice.STATUS_ISSUED)

    response = api_client.get(
        "/api/v1/invoices/",
        {"filter__status": Invoice.STATUS_PENDING, "filter__emission_type": Invoice.EMISSION_CONTINGENCY},
    )

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(invoice.pk)]


def test_bulk_resend_ignores_already_issued_invoices(
    api_client, account_with_financeiro, restaurant, branch, manager_user, monkeypatch
):
    retry_invoice = make_invoice(
        make_order(restaurant, branch, manager_user),
        emission_type=Invoice.EMISSION_CONTINGENCY,
    )
    issued_invoice = make_invoice(
        make_order(restaurant, branch, manager_user),
        status=Invoice.STATUS_ISSUED,
    )

    monkeypatch.setattr("apps.invoices.bulk.resend_fiscal_invoice", lambda invoice, user: invoice)
    response = api_client.post(
        "/api/v1/invoices/bulk-resend/",
        {"ids": [str(retry_invoice.pk), str(issued_invoice.pk)]},
        format="json",
    )

    assert response.status_code == 200, response.data
    assert response.data == {
        "requested": 2,
        "resent": 1,
        "skipped_issued": 1,
        "skipped_cancelled": 0,
        "failed": 0,
        "errors": [],
    }
