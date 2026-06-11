from django.forms.models import BaseInlineFormSet
from unfold.admin import ModelAdmin, TabularInline


def _model_has_field(model, field_name):
    return any(field.name == field_name for field in model._meta.fields)


def _tenant_queryset(model, account=None):
    manager = model.all_objects if hasattr(model, "all_objects") else model.objects
    queryset = manager.all()
    if _model_has_field(model, "deleted_at"):
        queryset = queryset.filter(deleted_at__isnull=True)
    if account and _model_has_field(model, "account"):
        queryset = queryset.filter(account=account)
    return queryset


class TenantAdminMixin:
    def get_request_account(self, request):
        account_id = request.headers.get("X-Account-ID") or request.GET.get("account")
        if request.user.is_superuser and account_id:
            from apps.accounts.models import Account

            return Account.objects.filter(id=account_id, is_active=True).first()

        profile = getattr(request.user, "profile", None)
        return getattr(profile, "account", None)

    def get_queryset(self, request):
        if not _model_has_field(self.model, "account"):
            return super().get_queryset(request)

        account = self.get_request_account(request)
        if request.user.is_superuser and account is None:
            return _tenant_queryset(self.model)
        if account is None:
            return _tenant_queryset(self.model).none()
        return _tenant_queryset(self.model, account=account)

    def save_model(self, request, obj, form, change):
        account = self.get_request_account(request)
        if _model_has_field(obj.__class__, "account") and not obj.account_id and account:
            obj.account = account
        super().save_model(request, obj, form, change)

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        account = self.get_request_account(request)
        related_model = db_field.remote_field.model

        if db_field.name == "account" and not request.user.is_superuser and account:
            kwargs["queryset"] = related_model.objects.filter(pk=account.pk)
        elif _model_has_field(related_model, "account"):
            if request.user.is_superuser and account is None:
                kwargs["queryset"] = _tenant_queryset(related_model)
            elif account:
                kwargs["queryset"] = _tenant_queryset(related_model, account=account)
            else:
                kwargs["queryset"] = _tenant_queryset(related_model).none()

        return super().formfield_for_foreignkey(db_field, request, **kwargs)


class TenantModelAdmin(TenantAdminMixin, ModelAdmin):
    pass


class TenantInlineFormSet(BaseInlineFormSet):
    def save_new(self, form, commit=True):
        obj = form.save(commit=False)
        parent = self.instance
        for field_name in ("account", "restaurant", "branch"):
            if _model_has_field(obj.__class__, field_name) and not getattr(obj, f"{field_name}_id", None):
                parent_value = getattr(parent, field_name, None)
                if parent_value is not None:
                    setattr(obj, field_name, parent_value)
        if commit:
            obj.save()
            form.save_m2m()
        return obj


class TenantTabularInline(TenantAdminMixin, TabularInline):
    formset = TenantInlineFormSet
