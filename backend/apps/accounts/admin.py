from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin

from apps.accounts.admin_forms import ACCOUNT_FIELDS, MODULE_FIELDS, AccountChangeForm, AccountCreationForm
from apps.accounts.models import Account, GlobalSystemConfig, Permission, Plan, Role, Subscription, UserProfile
from apps.core.admin_mixins import TenantModelAdmin


admin.site.unregister(User)
admin.site.unregister(Group)


@admin.register(User)
class StarChefUserAdmin(DjangoUserAdmin, ModelAdmin):
    list_display = ("username", "email", "first_name", "last_name", "account", "is_staff", "is_active", "last_login")
    list_filter = ("is_staff", "is_superuser", "is_active", "groups", "profile__account", "profile__profile_type")
    search_fields = ("username", "email", "first_name", "last_name", "profile__phone")

    def account(self, obj):
        profile = getattr(obj, "profile", None)
        return profile.account if profile else None

    def get_queryset(self, request):
        queryset = super().get_queryset(request).select_related("profile", "profile__account")
        if request.user.is_superuser:
            return queryset
        profile = getattr(request.user, "profile", None)
        if not profile or not profile.account_id:
            return queryset.none()
        return queryset.filter(profile__account_id=profile.account_id)


@admin.register(Group)
class StarChefGroupAdmin(DjangoGroupAdmin, ModelAdmin):
    search_fields = ("name",)


@admin.register(Permission)
class PermissionAdmin(ModelAdmin):
    list_display = ("code", "name")
    search_fields = ("code", "name")


@admin.register(Plan)
class PlanAdmin(ModelAdmin):
    list_display = ("code", "name", "max_branches", "max_users", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(Account)
class AccountAdmin(ModelAdmin):
    list_display = ("name", "slug", "status", "subscription_status", "plan", "max_restaurants", "max_users", "modules_summary", "is_active")
    list_filter = ("status", "subscription_status", "plan", "is_active")
    search_fields = ("name", "slug", "document", "email")
    prepopulated_fields = {"slug": ("name",)}

    _MODULE_FIELD_NAMES = tuple(MODULE_FIELDS.keys())

    @admin.display(description="Modulos")
    def modules_summary(self, obj):
        optionals = obj.enabled_modules or []
        return ", ".join(optionals) if optionals else "— (so base)"

    def get_form(self, request, obj=None, **kwargs):
        # Add: coleta tambem o primeiro admin da conta. Change: so conta + modulos.
        kwargs["form"] = AccountChangeForm if obj else AccountCreationForm
        return super().get_form(request, obj, **kwargs)

    def get_fieldsets(self, request, obj=None):
        account_section = ("Dados da conta", {"fields": tuple(ACCOUNT_FIELDS)})
        modules_section = (
            "Modulos ativos",
            {"fields": self._MODULE_FIELD_NAMES, "description": "Ative ou desative os modulos opcionais desta conta."},
        )
        if obj is None:
            admin_section = (
                "Primeiro usuario administrador",
                {
                    "fields": ("admin_username", "admin_email", "admin_first_name", "admin_last_name", "admin_password"),
                    "description": "Usuario admin criado junto com a conta (acesso total no app).",
                },
            )
            return (account_section, admin_section, modules_section)
        return (account_section, modules_section)

    def save_model(self, request, obj, form, change):
        # form.save(commit=False) (chamado pelo admin) ja aplicou enabled_modules ao obj.
        super().save_model(request, obj, form, change)
        # Ao criar, provisiona o primeiro usuario administrador vinculado a conta.
        if not change and isinstance(form, AccountCreationForm):
            form.create_admin_user(obj)


@admin.register(Subscription)
class SubscriptionAdmin(ModelAdmin):
    list_display = ("account", "plan", "status", "current_period_starts_at", "current_period_ends_at")
    list_filter = ("status", "plan")
    search_fields = ("account__name", "account__slug", "plan__name")


@admin.register(GlobalSystemConfig)
class GlobalSystemConfigAdmin(ModelAdmin):
    list_display = ("key", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("key", "description")


@admin.register(Role)
class RoleAdmin(TenantModelAdmin):
    list_display = ("name", "code", "account", "restaurant", "is_system")
    list_filter = ("account", "is_system", "restaurant")
    search_fields = ("name", "code")


@admin.register(UserProfile)
class UserProfileAdmin(TenantModelAdmin):
    list_display = ("user", "account", "profile_type", "restaurant", "branch", "is_active")
    list_filter = ("account", "profile_type", "restaurant", "branch", "is_active")
    search_fields = ("user__username", "user__email", "phone")
