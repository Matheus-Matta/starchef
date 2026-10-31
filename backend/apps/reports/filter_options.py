from django.db.models import Q

from apps.menu.models import ProductCategory
from apps.payments.models import CashStation
from apps.restaurants.models import Restaurant, TableSector


def _rows(queryset, *fields):
    return [
        {key: str(value) if key == "id" else value for key, value in zip(fields, values, strict=True)}
        for values in queryset.values_list(*fields)
    ]


def report_filter_options(request, section, report_filters):
    """Devolve na resposta as opções que obedecem ao mesmo escopo do relatório."""
    account = getattr(request, "account", None)
    if account is None:
        return {"restaurants": []}

    restaurant_id = request.query_params.get("restaurant") or report_filters.get("restaurant_id")
    restaurants = Restaurant.objects.filter(account=account, is_active=True).order_by("trade_name")
    options = {
        "restaurants": [
            {"id": str(row.id), "name": row.trade_name or row.legal_name}
            for row in restaurants.only("id", "trade_name", "legal_name")
        ],
    }

    if section == "products":
        categories = ProductCategory.objects.filter(account=account, is_active=True)
        sectors = TableSector.objects.filter(account=account, is_active=True)
        if restaurant_id:
            categories = categories.filter(Q(restaurant_id=restaurant_id) | Q(restaurant__isnull=True))
            sectors = sectors.filter(restaurant_id=restaurant_id)
        options["categories"] = _rows(categories.order_by("name"), "id", "name")
        options["sectors"] = _rows(sectors.order_by("name"), "id", "name")

    if section == "cash":
        stations = CashStation.objects.filter(account=account, is_active=True)
        if restaurant_id:
            stations = stations.filter(restaurant_id=restaurant_id)
        options["cash_stations"] = _rows(stations.order_by("name"), "id", "name", "code")

    return options
