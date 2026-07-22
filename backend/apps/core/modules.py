"""
Catalogo de modulos do sistema (arquitetura modular por conta/tenant).

O "Modulo Base" e obrigatorio e sempre acessivel para qualquer conta ativa.
Os demais sao opcionais e habilitados por conta em `Account.enabled_modules`.
Fonte unica de verdade para backend (permissao/seed) e documentacao.
"""

MODULE_BASE = "base"
MODULE_ECOMMERCE = "ecommerce"
MODULE_ENTREGA = "entrega"
MODULE_FINANCEIRO = "financeiro"
MODULE_LOGISTICA = "logistica"

# Modulos opcionais (podem ser ligados/desligados por conta).
OPTIONAL_MODULES = [MODULE_ECOMMERCE, MODULE_ENTREGA, MODULE_FINANCEIRO, MODULE_LOGISTICA]

# Todos os modulos, incluindo o base obrigatorio.
ALL_MODULES = [MODULE_BASE, *OPTIONAL_MODULES]

# Catalogo descritivo (usado no seed e potencialmente numa tela de assinatura).
MODULE_CATALOG = [
    {
        "key": MODULE_BASE,
        "label": "Modulo Base",
        "optional": False,
        "description": "Operacao essencial: PDV, Pedidos, KDS, Produtos, Clientes e configuracoes.",
    },
    {
        "key": MODULE_ECOMMERCE,
        "label": "E-commerce",
        "optional": True,
        "description": "Cardapio digital, vitrine virtual e recepcao de pedidos online.",
    },
    {
        "key": MODULE_ENTREGA,
        "label": "Entrega",
        "optional": True,
        "description": "Gestao logistica de delivery: entregadores, despacho e rastreamento.",
    },
    {
        "key": MODULE_FINANCEIRO,
        "label": "Financeiro",
        "optional": True,
        "description": "Backoffice financeiro: historico de pagamentos, conciliacao e relatorios.",
    },
    {
        "key": MODULE_LOGISTICA,
        "label": "Logistica",
        "optional": True,
        "description": "Estoque, locais de armazenamento e movimentacoes de insumos.",
    },
]


def account_active_modules(account):
    """Lista efetiva de modulos de uma conta (sempre inclui o base)."""
    enabled = list(getattr(account, "enabled_modules", None) or []) if account else []
    return [MODULE_BASE, *[m for m in OPTIONAL_MODULES if m in enabled]]
