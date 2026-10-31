from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.bulk_jobs.models import BulkJob
from apps.bulk_jobs.services import enqueue_bulk_job
from apps.orders.bulk_cancel import cancelar_em_massa
from apps.orders.bulk_delete import excluir_em_massa
from apps.orders.models import Order


def enqueue_order_cancel(request, queryset, *, authorize):
    ids = _ids(request.data, "cancelar")
    reason = request.data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise ValidationError("O motivo do cancelamento é obrigatório.")
    orders = list(queryset.filter(pk__in=ids))
    authorizations = {}
    for order in orders:
        key = str(order.restaurant_id)
        if key in authorizations:
            continue
        approved, approved_by, method = authorize(order)
        authorizations[key] = {
            "approved": approved,
            "approved_by_id": str(approved_by.pk) if approved_by else None,
            "method": method,
        }
    return enqueue_bulk_job(
        account=request.account,
        user=request.user,
        action=BulkJob.ORDER_CANCEL,
        payload={
            "ids": [str(order.pk) for order in orders],
            "reason": reason.strip(),
            "authorizations": authorizations,
        },
        total=len(ids),
    )


def enqueue_order_delete(request, queryset):
    ids = _ids(request.data, "excluir")
    visible = list(queryset.filter(pk__in=ids).values_list("pk", flat=True))
    return enqueue_bulk_job(
        account=request.account,
        user=request.user,
        action=BulkJob.ORDER_DELETE,
        payload={"ids": [str(pk) for pk in visible]},
        total=len(ids),
    )


def run_order_bulk_job(job):
    orders = list(Order.objects.select_related("restaurant").filter(pk__in=job.payload["ids"]))
    if job.action == BulkJob.ORDER_DELETE:
        return excluir_em_massa(orders, user=job.requested_by)

    User = get_user_model()
    by_restaurant = job.payload["authorizations"]

    def authorize(order):
        data = by_restaurant.get(str(order.restaurant_id), {})
        approved_by = None
        if data.get("approved_by_id"):
            approved_by = User.objects.filter(pk=data["approved_by_id"]).first()
        return bool(data.get("approved")), approved_by, data.get("method", "")

    return cancelar_em_massa(
        orders,
        user=job.requested_by,
        reason=job.payload["reason"],
        autorizar=authorize,
    )


def _ids(data, verb):
    from apps.orders.bulk_cancel import MAXIMO

    ids = data.get("ids") or []
    if not isinstance(ids, list) or not ids or len(ids) > MAXIMO:
        raise ValidationError({"ids": f"Selecione de 1 a {MAXIMO} pedidos para {verb}."})
    return list(dict.fromkeys(str(pk) for pk in ids))
