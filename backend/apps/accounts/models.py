from django.conf import settings
from django.db import models

from apps.core.models import TenantBaseModel, TimeStampedModel
from apps.core.modules import MODULE_BASE


class Plan(TimeStampedModel):
    code = models.CharField(max_length=60, unique=True)
    name = models.CharField(max_length=120)
    max_branches = models.PositiveIntegerField(default=1)
    max_users = models.PositiveIntegerField(default=5)
    features = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Account(TimeStampedModel):
    STATUS_ACTIVE = "active"
    STATUS_SUSPENDED = "suspended"
    STATUS_CANCELED = "canceled"

    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_SUSPENDED, "Suspended"),
        (STATUS_CANCELED, "Canceled"),
    ]

    SUBSCRIPTION_TRIAL = "trial"
    SUBSCRIPTION_ACTIVE = "active"
    SUBSCRIPTION_PAST_DUE = "past_due"
    SUBSCRIPTION_CANCELED = "canceled"

    SUBSCRIPTION_STATUS_CHOICES = [
        (SUBSCRIPTION_TRIAL, "Trial"),
        (SUBSCRIPTION_ACTIVE, "Active"),
        (SUBSCRIPTION_PAST_DUE, "Past due"),
        (SUBSCRIPTION_CANCELED, "Canceled"),
    ]

    name = models.CharField(max_length=150)
    slug = models.SlugField(unique=True)
    document = models.CharField(max_length=20, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    plan = models.ForeignKey(Plan, null=True, blank=True, related_name="accounts", on_delete=models.SET_NULL)
    timezone = models.CharField(max_length=50, default="America/Sao_Paulo")
    default_currency = models.CharField(max_length=3, default="BRL")
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    subscription_status = models.CharField(
        max_length=30,
        choices=SUBSCRIPTION_STATUS_CHOICES,
        default=SUBSCRIPTION_TRIAL,
    )
    # Licenciamento modular: lista de modulos OPCIONAIS habilitados para a conta.
    # O modulo base e sempre implicito (ver has_module / account_active_modules).
    enabled_modules = models.JSONField(default=list, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["status", "is_active"]),
        ]

    def __str__(self):
        return self.name

    def has_module(self, module_key):
        """True se a conta pode acessar o modulo (base sempre liberado)."""
        if module_key == MODULE_BASE:
            return True
        return module_key in (self.enabled_modules or [])


class Subscription(TimeStampedModel):
    account = models.OneToOneField(Account, related_name="subscription", on_delete=models.CASCADE)
    plan = models.ForeignKey(Plan, related_name="subscriptions", on_delete=models.PROTECT)
    status = models.CharField(max_length=30, default=Account.SUBSCRIPTION_TRIAL)
    current_period_starts_at = models.DateTimeField(null=True, blank=True)
    current_period_ends_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.account} - {self.plan}"


class GlobalSystemConfig(TimeStampedModel):
    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.key


class Permission(TimeStampedModel):
    code = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.code


class Role(TenantBaseModel):
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=120)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="roles",
        on_delete=models.CASCADE,
    )
    permissions = models.ManyToManyField(Permission, blank=True, related_name="roles")
    max_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    is_system = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["account", "code"], name="unique_role_by_account"),
        ]

    def __str__(self):
        return self.name


class UserProfile(TenantBaseModel):
    PROFILE_ADMIN = "admin"
    PROFILE_OWNER = "owner"
    PROFILE_MANAGER = "manager"
    PROFILE_WAITER = "waiter"
    PROFILE_KITCHEN = "kitchen"
    PROFILE_CASHIER = "cashier"
    PROFILE_DRIVER = "driver"

    PROFILE_CHOICES = [
        (PROFILE_ADMIN, "Administrator"),
        (PROFILE_OWNER, "Owner"),
        (PROFILE_MANAGER, "Manager"),
        (PROFILE_WAITER, "Waiter"),
        (PROFILE_KITCHEN, "Kitchen"),
        (PROFILE_CASHIER, "Cashier"),
        (PROFILE_DRIVER, "Driver"),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE)
    phone = models.CharField(max_length=32, blank=True)
    profile_type = models.CharField(max_length=24, choices=PROFILE_CHOICES, default=PROFILE_WAITER)
    role = models.ForeignKey(Role, null=True, blank=True, related_name="user_profiles", on_delete=models.SET_NULL)
    restaurant = models.ForeignKey(
        "restaurants.Restaurant",
        null=True,
        blank=True,
        related_name="user_profiles",
        on_delete=models.PROTECT,
    )
    branch = models.ForeignKey(
        "restaurants.Branch",
        null=True,
        blank=True,
        related_name="user_profiles",
        on_delete=models.PROTECT,
    )
    specific_permissions = models.ManyToManyField(Permission, blank=True, related_name="user_profiles")
    last_login_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    class Meta:
        indexes = [
            models.Index(fields=["account", "profile_type"]),
            models.Index(fields=["restaurant", "branch", "profile_type"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username} ({self.profile_type})"
