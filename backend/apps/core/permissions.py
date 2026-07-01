from rest_framework.permissions import BasePermission

from apps.core.access import is_tenant_admin


class HasTenantAccess(BasePermission):
    message = "Access denied for this account, restaurant or branch."

    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated):
            return False
        if is_tenant_admin(request.user):
            return True
        return getattr(request, "account", None) is not None

    def has_object_permission(self, request, view, obj):
        user = request.user
        if user.is_superuser:
            return True

        request_account = getattr(request, "account", None)
        object_account_id = getattr(obj, "account_id", None)
        if object_account_id and (not request_account or request_account.id != object_account_id):
            return False

        if is_tenant_admin(user):
            return True

        profile = getattr(user, "profile", None)
        if not profile:
            return False

        object_restaurant_id = getattr(obj, "restaurant_id", None)
        if object_restaurant_id is None and obj._meta.label == "restaurants.Restaurant":
            object_restaurant_id = obj.id
        object_branch_id = getattr(obj, "branch_id", None)

        if object_restaurant_id and profile.restaurant_id != object_restaurant_id:
            return False
        if object_branch_id and profile.branch_id and profile.branch_id != object_branch_id:
            return False

        return True


class IsSameAccountPermission(BasePermission):
    message = "Object does not belong to the authenticated account."

    def has_permission(self, request, view):
        return bool(getattr(request, "account", None) or request.user.is_superuser)

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        account = getattr(request, "account", None)
        return bool(account and hasattr(obj, "account_id") and obj.account_id == account.id)


class CanManageCashRegister(BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.profile_type in {"admin", "owner", "manager", "cashier"})


class CanAuthorizeDiscount(BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, "profile", None)
        return bool(profile and profile.profile_type in {"admin", "owner", "manager"})
