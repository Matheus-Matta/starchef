import contextvars
from contextlib import contextmanager

from apps.core.models import AuditLog


def _instance_restaurant_and_branch(instance):
    restaurant = getattr(instance, "restaurant", None)
    branch = getattr(instance, "branch", None)

    if instance._meta.label_lower == "restaurants.restaurant":
        restaurant = instance
    elif instance._meta.label_lower == "restaurants.branch":
        branch = instance
        restaurant = instance.restaurant

    return restaurant, branch


def _audit_account(instance, restaurant, branch, actor=None, request=None):
    if getattr(instance, "account_id", None):
        return instance.account
    if getattr(restaurant, "account_id", None):
        return restaurant.account
    if getattr(branch, "account_id", None):
        return branch.account
    if request and getattr(request, "account", None):
        return request.account

    profile = getattr(actor, "profile", None)
    if profile and getattr(profile, "account_id", None):
        return profile.account
    return None


def record_audit(
    *,
    action,
    instance,
    actor=None,
    reason="",
    changes=None,
    metadata=None,
    request=None,
):
    restaurant, branch = _instance_restaurant_and_branch(instance)
    account = _audit_account(instance, restaurant, branch, actor=actor, request=request)
    if account is None:
        return None

    ip_address = None

    if request:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip_address = forwarded.split(",")[0] if forwarded else request.META.get("REMOTE_ADDR")

    registro = AuditLog(
        account=account,
        restaurant=restaurant,
        branch=branch,
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        entity=instance.__class__.__name__,
        object_id=str(instance.pk),
        reason=reason,
        changes=changes or {},
        metadata=metadata or {},
        ip_address=ip_address,
    )
    # Dentro da venda, a auditoria sai junta no fim (`auditoria_em_lote`).
    pendentes = _lote.get()
    if pendentes is not None:
        if pendentes is not _DESCARTAR:
            pendentes.append(registro)
        return registro
    registro.save()
    return registro


_DESCARTAR = object()
_lote = contextvars.ContextVar("auditoria_lote", default=None)


@contextmanager
def auditoria_em_lote(*, descartar=False):
    """Junta a auditoria do bloco e a grava de uma vez no fim (ou nenhuma).

    Uma venda de 50 itens gravava 154 registros, um por vez (~0,34 s). Em
    lote, uma inserção, e cada registro dispara o seu `post_save` como antes
    (`core/lote.py`) — a auditoria sincroniza. `descartar` é para o que vai ser
    desfeito de qualquer jeito: a simulação da venda.
    """
    if _lote.get() is not None:  # dentro de outro lote: quem abriu grava
        yield
        return
    pendentes = _DESCARTAR if descartar else []
    token = _lote.set(pendentes)
    try:
        yield
    finally:
        _lote.reset(token)
    if pendentes is not _DESCARTAR:
        from apps.core.lote import criar_em_lote

        criar_em_lote(AuditLog, pendentes)
