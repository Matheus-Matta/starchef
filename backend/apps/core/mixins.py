from rest_framework.exceptions import ValidationError

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.tenant import set_current_account


def model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


class TenantQuerySetMixin:
    tenant_branch_field = "branch"
    tenant_restaurant_field = "restaurant"

    def get_queryset(self):
        base_queryset = super().get_queryset()
        model = base_queryset.model
        if hasattr(model, "all_objects"):
            queryset = model.all_objects.all()
            if model_has_field(model, "deleted_at"):
                queryset = queryset.filter(deleted_at__isnull=True)
        else:
            queryset = base_queryset

        user = self.request.user
        account = getattr(self.request, "account", None)

        if account is not None:
            set_current_account(account)
            if model_has_field(queryset.model, "account"):
                queryset = queryset.filter(account=account)

        if not user.is_authenticated:
            return queryset.none()

        if is_tenant_admin(user):
            return self._apply_admin_scope_filters(queryset)

        profile = getattr(user, "profile", None)
        if not profile:
            return queryset.none()

        model_is_restaurant_scoped = (
            queryset.model._meta.label == "restaurants.Restaurant"
            or model_has_field(queryset.model, self.tenant_restaurant_field)
        )
        if model_is_restaurant_scoped and not profile.restaurant_id:
            return queryset.none()

        filters = {}
        if profile.restaurant_id:
            if queryset.model._meta.label == "restaurants.Restaurant":
                filters["id"] = profile.restaurant_id
            elif model_has_field(queryset.model, self.tenant_restaurant_field):
                filters[f"{self.tenant_restaurant_field}_id"] = profile.restaurant_id
        if profile.branch_id and model_has_field(queryset.model, self.tenant_branch_field):
            filters[f"{self.tenant_branch_field}_id"] = profile.branch_id

        return queryset.filter(**filters) if filters else queryset

    def get_object(self):
        obj = super().get_object()
        account = getattr(self.request, "account", None)
        if account is not None and hasattr(obj, "account_id") and obj.account_id != account.id:
            from django.http import Http404

            raise Http404()
        return obj

    def _apply_admin_scope_filters(self, queryset):
        restaurant_id = self.request.query_params.get(self.tenant_restaurant_field)
        branch_id = self.request.query_params.get(self.tenant_branch_field)
        filters = {}

        if restaurant_id:
            if queryset.model._meta.label == "restaurants.Restaurant":
                filters["id"] = restaurant_id
            elif model_has_field(queryset.model, self.tenant_restaurant_field):
                filters[f"{self.tenant_restaurant_field}_id"] = restaurant_id

        if branch_id:
            if queryset.model._meta.label == "restaurants.Branch":
                filters["id"] = branch_id
            elif model_has_field(queryset.model, self.tenant_branch_field):
                filters[f"{self.tenant_branch_field}_id"] = branch_id

        return queryset.filter(**filters) if filters else queryset


class AuditCreateUpdateMixin:
    def perform_create(self, serializer):
        extra = {}
        model_fields = {field.name for field in serializer.Meta.model._meta.fields}
        user = self.request.user
        profile = getattr(user, "profile", None)
        account = getattr(self.request, "account", None) or getattr(profile, "account", None)

        if "account" in serializer.validated_data:
            serializer.validated_data.pop("account")
        if "account" in model_fields and account:
            extra["account"] = account
        elif "account" in model_fields:
            raise ValidationError({"account": "Contexto de conta e obrigatorio."})
        if serializer.Meta.model._meta.label == "restaurants.Restaurant" and profile and not is_tenant_admin(user):
            raise ValidationError({"restaurant": "Apenas admin pode criar restaurantes."})
        if "created_by" in model_fields:
            extra["created_by"] = user
        if "updated_by" in model_fields:
            extra["updated_by"] = user
        if "restaurant" in serializer.validated_data and profile and not is_tenant_admin(user):
            restaurant = serializer.validated_data["restaurant"]
            if profile.restaurant_id and restaurant and restaurant.id != profile.restaurant_id:
                raise ValidationError({"restaurant": "Restaurante fora do escopo do usuario."})
        if "branch" in serializer.validated_data and profile and not is_tenant_admin(user):
            branch = serializer.validated_data["branch"]
            if profile.branch_id and branch and branch.id != profile.branch_id:
                raise ValidationError({"branch": "Filial fora do escopo do usuario."})
            if profile.restaurant_id and branch and branch.restaurant_id != profile.restaurant_id:
                raise ValidationError({"branch": "Filial pertence a outro restaurante."})

        if "restaurant" in model_fields and "restaurant" not in serializer.validated_data and profile:
            extra["restaurant"] = profile.restaurant
        if "branch" in model_fields and "branch" not in serializer.validated_data and profile:
            extra["branch"] = profile.branch

        instance = serializer.save(**{k: v for k, v in extra.items() if v is not None})
        record_audit(action=AuditLog.ACTION_CREATED, instance=instance, actor=user, request=self.request)

    def perform_update(self, serializer):
        extra = {}
        model_fields = {field.name for field in serializer.Meta.model._meta.fields}
        if "account" in serializer.validated_data:
            serializer.validated_data.pop("account")
        user = self.request.user
        profile = getattr(user, "profile", None)
        if "restaurant" in serializer.validated_data and profile and not is_tenant_admin(user):
            restaurant = serializer.validated_data["restaurant"]
            if profile.restaurant_id and restaurant and restaurant.id != profile.restaurant_id:
                raise ValidationError({"restaurant": "Restaurante fora do escopo do usuario."})
        if "branch" in serializer.validated_data and profile and not is_tenant_admin(user):
            branch = serializer.validated_data["branch"]
            if profile.branch_id and branch and branch.id != profile.branch_id:
                raise ValidationError({"branch": "Filial fora do escopo do usuario."})
            if profile.restaurant_id and branch and branch.restaurant_id != profile.restaurant_id:
                raise ValidationError({"branch": "Filial pertence a outro restaurante."})
        if "updated_by" in model_fields:
            extra["updated_by"] = self.request.user

        instance = serializer.save(**extra)
        record_audit(action=AuditLog.ACTION_UPDATED, instance=instance, actor=self.request.user, request=self.request)
