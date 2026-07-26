import zlib
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.models import Account, Permission, Plan, Role, Subscription, UserProfile
from apps.accounts.permission_catalog import iter_permissions
from apps.core.modules import OPTIONAL_MODULES
from apps.core.tenant import tenant_context
from apps.restaurants.models import Branch, Restaurant

DEFAULT_ACCOUNT_SLUG = "starchef-demo"
DEFAULT_ACCOUNT_NAME = "StarChef Demo"
DEFAULT_RESTAURANT_NAME = "Burger Palace"
DEFAULT_BRANCH_NAME = "Copacabana"
DEFAULT_USERNAME = "admin"
DEFAULT_EMAIL = "admin@starchef.test"
DEFAULT_PASSWORD = "admin12345"


def ensure_demo_plan():
    plan, _ = Plan.objects.update_or_create(
        code="demo",
        defaults={
            "name": "Demo",
            "max_branches": 5,
            "max_users": 50,
            "features": {
                "orders": True,
                "kitchen": True,
                "stock": True,
                "payments": True,
                "reports": True,
                "delivery": True,
                "digital_menu": True,
            },
            "is_active": True,
        },
    )
    return plan


def ensure_base_tenant(
    *,
    account_slug=DEFAULT_ACCOUNT_SLUG,
    account_name=DEFAULT_ACCOUNT_NAME,
    restaurant_name=DEFAULT_RESTAURANT_NAME,
    branch_name=DEFAULT_BRANCH_NAME,
    restaurant_city="São Paulo",
    restaurant_state="SP",
    restaurant_address="Rua das Panelas, 100",
    restaurant_phone="(11) 4000-0100",
    restaurant_email="contato@starchef.test",
):
    plan = ensure_demo_plan()
    now = timezone.now()
    account, _ = Account.objects.update_or_create(
        slug=account_slug,
        defaults={
            "name": account_name,
            "document": _unique_document(account_slug),
            "email": f"contato@{account_slug}.test",
            "phone": "(11) 4000-0000",
            "status": Account.STATUS_ACTIVE,
            "plan": plan,
            "trial_ends_at": now + timedelta(days=30),
            "subscription_status": Account.SUBSCRIPTION_TRIAL,
            # Contas demo com todos os modulos opcionais habilitados.
            "enabled_modules": list(OPTIONAL_MODULES),
            # Limites de tenancy da conta demo (0 = ilimitado). Generosos p/ demonstrar.
            "max_users": plan.max_users,
            "max_restaurants": 10,
            "is_active": True,
        },
    )
    Subscription.objects.update_or_create(
        account=account,
        defaults={
            "plan": plan,
            "status": Account.SUBSCRIPTION_TRIAL,
            "current_period_starts_at": now,
            "current_period_ends_at": now + timedelta(days=30),
            "metadata": {"source": "seed_demo"},
        },
    )

    with tenant_context(account):
        restaurant = Restaurant.all_objects.filter(account=account, trade_name=restaurant_name).first()
        restaurant_defaults = {
            "account": account,
            "legal_name": f"{restaurant_name} Ltda",
            "trade_name": restaurant_name,
            "cnpj": _unique_document(f"{account_slug}-r1"),
            "phone": restaurant_phone,
            "email": restaurant_email,
            "address": restaurant_address,
            "city": restaurant_city,
            "state": restaurant_state,
            "zip_code": "01000-000",
            "default_service_fee_percent": Decimal("10.00"),
            "operational_settings": {"accepts_delivery": True, "accepts_tables": True},
            "fiscal_settings": {"demo": True},
            "print_settings": {"demo": True},
            "is_active": True,
        }
        if restaurant is None:
            restaurant = Restaurant.all_objects.create(**restaurant_defaults)
        else:
            _update_instance(restaurant, restaurant_defaults, skip_fields={"account", "cnpj"})

        branch, _ = Branch.all_objects.update_or_create(
            account=account,
            restaurant=restaurant,
            name=branch_name,
            defaults={
                "phone": restaurant_phone,
                "email": restaurant_email,
                "address": restaurant_address,
                "city": restaurant_city,
                "state": restaurant_state,
                "zip_code": "01000-000",
                "opening_hours": {"seg_sex": "11:00-23:00", "sab_dom": "12:00-23:30"},
                "default_service_fee_percent": Decimal("10.00"),
                "require_open_cash_register": True,
                "stock_deduction_timing": Branch.STOCK_DEDUCTION_PAYMENT,
                "print_settings": {"demo": True},
                "fiscal_settings": {"demo": True},
                "is_active": True,
            },
        )

    return account, restaurant, branch


def ensure_restaurant_in_account(
    account,
    *,
    restaurant_name,
    branch_name,
    cnpj_seed,
    city="São Paulo",
    state="SP",
    address="",
    phone="",
    email="",
    service_fee_percent="10.00",
):
    """Add an extra restaurant (with one branch) to an existing account."""
    with tenant_context(account):
        restaurant = Restaurant.all_objects.filter(account=account, trade_name=restaurant_name).first()
        defaults = {
            "account": account,
            "legal_name": f"{restaurant_name} Ltda",
            "trade_name": restaurant_name,
            "cnpj": _unique_document(cnpj_seed),
            "phone": phone,
            "email": email,
            "address": address,
            "city": city,
            "state": state,
            "zip_code": "20000-000",
            "default_service_fee_percent": Decimal(service_fee_percent),
            "operational_settings": {"accepts_delivery": True, "accepts_tables": True},
            "fiscal_settings": {"demo": True},
            "print_settings": {"demo": True},
            "is_active": True,
        }
        if restaurant is None:
            restaurant = Restaurant.all_objects.create(**defaults)
        else:
            _update_instance(restaurant, defaults, skip_fields={"account", "cnpj"})

        branch, _ = Branch.all_objects.update_or_create(
            account=account,
            restaurant=restaurant,
            name=branch_name,
            defaults={
                "phone": phone,
                "email": email,
                "address": address,
                "city": city,
                "state": state,
                "zip_code": "20000-000",
                "opening_hours": {"seg_sex": "12:00-23:00", "sab_dom": "12:00-00:00"},
                "default_service_fee_percent": Decimal(service_fee_percent),
                "require_open_cash_register": True,
                "stock_deduction_timing": Branch.STOCK_DEDUCTION_PAYMENT,
                "print_settings": {"demo": True},
                "fiscal_settings": {"demo": True},
                "is_active": True,
            },
        )

    return restaurant, branch


def ensure_permissions():
    """Sincroniza o catálogo canônico e devolve um dict code -> Permission."""
    for code, defaults in iter_permissions():
        Permission.objects.update_or_create(code=code, defaults=defaults)
    return {perm.code: perm for perm in Permission.objects.all()}


def ensure_role(account, *, code, name, restaurant=None, permissions=None, max_discount_percent=0, is_system=True):
    with tenant_context(account):
        role, _ = Role.all_objects.update_or_create(
            account=account,
            code=code,
            defaults={
                "name": name,
                "restaurant": restaurant,
                "max_discount_percent": Decimal(str(max_discount_percent)),
                "is_system": is_system,
                "is_active": True,
            },
        )
        if permissions is not None:
            role.permissions.set(permissions)
        return role


def ensure_tenant_user(
    *,
    account,
    username,
    email,
    password,
    first_name="Demo",
    last_name="User",
    profile_type=UserProfile.PROFILE_OWNER,
    restaurant=None,
    branch=None,
    role=None,
    phone="",
    is_staff=False,
    is_superuser=False,
):
    User = get_user_model()
    user, _ = User.objects.get_or_create(username=username)
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.is_active = True
    user.is_staff = is_staff
    user.is_superuser = is_superuser
    if password:
        user.set_password(password)
    user.save()

    with tenant_context(account):
        profile, _ = UserProfile.all_objects.get_or_create(
            user=user,
            defaults={
                "account": account,
                "profile_type": profile_type,
                "restaurant": restaurant,
                "branch": branch,
                "role": role,
                "phone": phone,
                "is_active": True,
            },
        )
        profile.account = account
        profile.profile_type = profile_type
        profile.restaurant = restaurant
        profile.branch = branch
        profile.role = role
        profile.phone = phone
        profile.is_active = True
        profile.save()

    return user


def ensure_demo_roles(account, restaurant):
    permissions = ensure_permissions()

    def pick(*codes):
        """Seleciona permissões por código (ignora as ausentes, defensivo)."""
        return [permissions[code] for code in codes if code in permissions]

    roles = {
        # admin e owner enxergam tudo (todos os itens do catálogo).
        "admin": ensure_role(
            account,
            code="admin",
            name="Administrador",
            restaurant=restaurant,
            permissions=permissions.values(),
            max_discount_percent=100,
        ),
        "owner": ensure_role(
            account,
            code="owner",
            name="Proprietario",
            restaurant=restaurant,
            permissions=permissions.values(),
            max_discount_percent=100,
        ),
        # Gerente: opera o restaurante inteiro, inclusive todos os caixas.
        "manager": ensure_role(
            account,
            code="manager",
            name="Gerente",
            restaurant=restaurant,
            permissions=pick(
                "orders.view", "orders.manage", "orders.cancel", "orders.discount", "orders.create",
                "cash.view", "cash.open", "cash.manage", "cash.approve", "cash.withdrawal", "cash.supply",
                "payments.manage", "menu.manage", "stock.manage", "reports.view", "devices.manage",
                "users.manage", "tables.manage", "customers.manage", "kitchen.manage",
            ),
            max_discount_percent=30,
        ),
        # Garçom: cuida apenas dos próprios pedidos e das mesas/comandas.
        "waiter": ensure_role(
            account,
            code="waiter",
            name="Garcom",
            restaurant=restaurant,
            permissions=pick(
                "orders.view.own", "orders.create", "orders.manage",
                "tables.view", "tables.manage", "menu.view", "customers.view", "kitchen.view",
            ),
            max_discount_percent=5,
        ),
        # Cozinha: acompanha e opera o KDS.
        "kitchen": ensure_role(
            account,
            code="kitchen",
            name="Cozinha",
            restaurant=restaurant,
            permissions=pick("orders.view", "kitchen.view", "kitchen.manage"),
            max_discount_percent=0,
        ),
        # Caixa: gerencia SOMENTE o próprio caixa (abrir, fechar, sangria, suprimento).
        "cashier": ensure_role(
            account,
            code="cashier",
            name="Caixa",
            restaurant=restaurant,
            permissions=pick(
                "orders.view", "cash.view.own", "cash.open", "cash.close.own", "cash.manage.own",
                "cash.withdrawal", "cash.supply", "payments.manage", "menu.view",
            ),
            max_discount_percent=10,
        ),
    }
    return roles


def _unique_document(seed):
    base = zlib.adler32(seed.encode("utf-8")) % 10000
    for offset in range(10000):
        suffix = (base + offset) % 10000
        document = f"00.000.000/{suffix:04d}-00"
        owner = Restaurant.all_objects.filter(cnpj=document).first()
        if owner is None:
            return document
    return "00.000.000/0000-00"


def _update_instance(instance, values, skip_fields=None):
    skip_fields = skip_fields or set()
    changed_fields = []
    for field, value in values.items():
        if field in skip_fields:
            continue
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed_fields.append(field)
    if changed_fields:
        instance.save(update_fields=changed_fields + ["updated_at"])
