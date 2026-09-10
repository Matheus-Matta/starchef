"""Catálogo dos Perfis de Acesso (Role) fixos do sistema.

A partir desta mudança, "Perfis de Acesso" deixou de ser um cadastro livre por
conta: toda conta nasce com exatamente estes perfis, nesta ordem crescente de
acesso, e a tela/API de Perfis passou a ser somente leitura (ver
``RoleViewSet``). Para adicionar um novo perfil fixo no futuro, basta somar
uma entrada em ``SYSTEM_ROLES`` — a provisão (signal + migration) é genérica.

Convenção: cada perfil "herda" os códigos do perfil anterior e soma os seus
próprios, refletindo a hierarquia pedida (Garçom ⊂ Caixa ⊂ Gerente). O
Administrador tem acesso total: sempre o catálogo inteiro (``ALL_CODES``),
então ele nunca fica desatualizado quando um novo código é criado.
"""

from apps.accounts.permission_catalog import ALL_CODES

CODE_WAITER = "waiter"
CODE_CASHIER = "cashier"
CODE_MANAGER = "manager"
CODE_ADMIN = "admin"
CODE_ECOMMERCE = "ecommerce"

# Garçom: abrir, editar e acompanhar os próprios pedidos e as mesas/comandas.
_WAITER_CODES = [
    "orders.view.own",
    "orders.create",
    "orders.manage",
    "tables.view",
    "tables.manage",
    "menu.view",
    "customers.view",
    "kitchen.view",
]

# Caixa: tudo do garçom + enxergar todos os pedidos (fecha conta de qualquer
# mesa/garçom) + abrir/fechar caixa, sangria/suprimento e receber pagamentos.
_CASHIER_CODES = _WAITER_CODES + [
    "orders.view",
    "cash.view.own",
    "cash.open",
    "cash.close.own",
    "cash.manage.own",
    "cash.withdrawal",
    "cash.supply",
    "payments.manage",
]

# Gerente: tudo do caixa + controle da operação (cardápio, equipamentos,
# equipe, todos os caixas, cancelamento/desconto e relatórios).
_MANAGER_CODES = _CASHIER_CODES + [
    "cash.view",
    "cash.manage",
    "cash.approve",
    "orders.cancel",
    "orders.discount",
    "menu.manage",
    "devices.manage",
    "users.view",
    "users.manage",
    "customers.manage",
    "kitchen.manage",
    "reports.view.own",
    "reports.view",
    "stock.manage",
]

# E-commerce: o perfil de quem cuida do site/cardápio digital. Não é um degrau
# da hierarquia do salão — é uma especialidade paralela. Ele monta, publica e
# gerencia as imagens do storefront, e só enxerga do resto o cardápio (precisa
# saber quais produtos existem para montar a vitrine). Domínio fica de fora de
# propósito: apontar DNS errado tira o site do ar, então é do Administrador.
_ECOMMERCE_CODES = [
    "menu.view",
    "storefront.view",
    "storefront.edit",
    "storefront.publish",
    "storefront.assets",
]


def _dedupe(codes):
    return list(dict.fromkeys(codes))


# Ordem da lista = ordem de exibição. O `rank` é separado de propósito: ele é a
# hierarquia de autoridade lida por `has_role_at_least`, e nem todo perfil novo
# entra nessa escada. O de E-commerce, por exemplo, edita o site mas não pode
# herdar nada do caixa — daí um rank abaixo do garçom, e não a posição na lista.
SYSTEM_ROLES = [
    {
        "code": CODE_WAITER,
        "name": "Garçom",
        "rank": 10,
        "permissions": _dedupe(_WAITER_CODES),
        "max_discount_percent": 0,
        "is_account_admin": False,
    },
    {
        "code": CODE_CASHIER,
        "name": "Caixa",
        "rank": 20,
        "permissions": _dedupe(_CASHIER_CODES),
        "max_discount_percent": 0,
        "is_account_admin": False,
    },
    {
        "code": CODE_MANAGER,
        "name": "Gerente",
        "rank": 30,
        "permissions": _dedupe(_MANAGER_CODES),
        "max_discount_percent": 30,
        "is_account_admin": False,
    },
    {
        "code": CODE_ADMIN,
        "name": "Administrador",
        "rank": 40,
        # Sempre o catálogo inteiro — acesso total aos dados da conta.
        "permissions": list(ALL_CODES),
        "max_discount_percent": 100,
        "is_account_admin": True,
    },
    {
        "code": CODE_ECOMMERCE,
        "name": "E-commerce",
        "rank": 5,
        "permissions": _dedupe(_ECOMMERCE_CODES),
        "max_discount_percent": 0,
        "is_account_admin": False,
    },
]

SYSTEM_ROLE_CODES = [spec["code"] for spec in SYSTEM_ROLES]
# {código: nível de autoridade} — consumido por `apps.core.access`.
SYSTEM_ROLE_RANKS = {spec["code"]: spec["rank"] for spec in SYSTEM_ROLES}


def ensure_system_roles(account):
    """Upsert idempotente dos perfis fixos numa conta. Retorna {code: Role}."""
    from apps.accounts.models import Permission, Role

    permissions_by_code = {p.code: p for p in Permission.objects.filter(code__in=ALL_CODES)}

    roles = {}
    for spec in SYSTEM_ROLES:
        role, _created = Role.all_objects.update_or_create(
            account=account,
            code=spec["code"],
            defaults={
                "name": spec["name"],
                "restaurant": None,
                "max_discount_percent": spec["max_discount_percent"],
                "is_account_admin": spec["is_account_admin"],
                "is_system": True,
                "is_active": True,
            },
        )
        matched_permissions = [permissions_by_code[code] for code in spec["permissions"] if code in permissions_by_code]
        role.permissions.set(matched_permissions)
        roles[spec["code"]] = role
    return roles
