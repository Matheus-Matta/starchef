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

    return AuditLog.all_objects.create(
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
