import pytest
from rest_framework_simplejwt.tokens import AccessToken


@pytest.mark.django_db
def test_sales_report_exposes_dedicated_report_metrics(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.get(
        "/api/v1/reports/sales/",
        {"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )

    assert response.status_code == 200
    assert {
        "total",
        "average_ticket",
        "orders_total",
        "orders_open",
        "orders_cancelled",
        "payments_total",
        "payments_count",
        "payments_refunded",
        "items_quantity",
        "by_status",
        "by_order_type",
        "by_cancellation_reason",
        "by_payment_method",
        "by_restaurant",
        "by_waiter",
        "by_product",
    } <= response.data.keys()


@pytest.mark.django_db
def test_sales_report_rejects_inverted_period(api_client, manager_user):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.get(
        "/api/v1/reports/sales/",
        {"date_from": "2026-07-31", "date_to": "2026-07-01"},
    )

    assert response.status_code == 400
    assert "data inicial" in response.data["detail"].lower()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("path", "result_key"),
    [
        ("/api/v1/reports/orders/", "by_status"),
        ("/api/v1/reports/products/", "by_product"),
        ("/api/v1/reports/payments/", "by_payment_method"),
        ("/api/v1/reports/waiters/", "by_waiter"),
        ("/api/v1/reports/restaurants/", "by_restaurant"),
    ],
)
def test_dedicated_reports_are_paginated(api_client, manager_user, path, result_key):
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(manager_user)}")

    response = api_client.get(
        path,
        {
            "date_from": "2026-01-01",
            "date_to": "2026-12-31",
            "restaurant": str(manager_user.profile.restaurant_id),
            "page": 1,
            "page_size": 10,
        },
    )

    assert response.status_code == 200
    assert result_key in response.data
    assert response.data["pagination"][result_key]["page_size"] == 10
    assert response.data["filters"]["restaurant"] == str(manager_user.profile.restaurant_id)
