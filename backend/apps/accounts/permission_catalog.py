"""
Catálogo canônico de permissões de negócio — fonte única da verdade.

Cada permissão é um "item" atômico que pode ser atribuído a um Perfil de Acesso
(``Role``) ou diretamente ao usuário (``UserProfile.specific_permissions``). Os
itens são organizados em GRUPOS para facilitar a seleção na tela de Perfis.

O foco é o Módulo Base (operação do dia a dia). Itens de módulos opcionais ficam
no fim, marcados com ``module`` diferente de ``base`` — mantidos aqui apenas para
não perder códigos já usados em outras partes do sistema.

Convenção de código: ``"<area>.<acao>[.own]"``
  - o sufixo ``.own`` indica a versão restrita ao próprio operador ("meu"/"meus").
    Ex.: ``orders.view.own`` (ver *meus* pedidos) vs ``orders.view`` (ver todos);
    ``cash.manage.own`` (gerenciar *somente meu* caixa) vs ``cash.manage`` (todos).

Para aplicar o catálogo no banco use o comando ``manage.py sync_permissions``.
"""

MODULE_BASE = "base"

# Estrutura: (rótulo do grupo, módulo, [(código, nome, descrição), ...]).
# A ordem desta lista define o `sort_order` (e, portanto, a ordem de exibição).
PERMISSION_GROUPS = [
    (
        "Pedidos",
        MODULE_BASE,
        [
            ("orders.view.own", "Ver meus pedidos", "Enxerga apenas os pedidos abertos pelo próprio operador."),
            ("orders.view", "Ver todos os pedidos", "Enxerga os pedidos de todo o restaurante/filial."),
            ("orders.create", "Criar pedidos", "Abrir novos pedidos no PDV."),
            ("orders.manage", "Gerenciar pedidos", "Editar itens, reabrir e alterar pedidos existentes."),
            ("orders.cancel", "Cancelar pedidos", "Cancelar pedidos já abertos."),
            ("orders.discount", "Aplicar descontos", "Conceder desconto no pedido (respeitando o limite do perfil)."),
        ],
    ),
    (
        "Caixa",
        MODULE_BASE,
        [
            ("cash.view.own", "Ver meu caixa", "Consulta apenas a própria sessão de caixa."),
            ("cash.view", "Ver todos os caixas", "Consulta as sessões de caixa do restaurante/filial."),
            ("cash.open", "Abrir caixa", "Abrir uma nova sessão de caixa."),
            ("cash.close.own", "Fechar meu caixa", "Fechar a própria sessão de caixa."),
            ("cash.manage.own", "Gerenciar somente meu caixa", "Sangria/suprimento apenas na própria sessão de caixa."),
            ("cash.manage", "Gerenciar todos os caixas", "Operar e fechar qualquer sessão de caixa."),
            ("cash.withdrawal", "Sangria (retirada)", "Registrar retirada de dinheiro do caixa."),
            ("cash.supply", "Suprimento (reforço)", "Registrar entrada/reforço de dinheiro no caixa."),
            ("cash.approve", "Aprovar operações do caixa", "Autorizar sangria/suprimento/desconto (nível gerencial)."),
            ("payments.manage", "Gerenciar pagamentos", "Receber e estornar pagamentos."),
        ],
    ),
    (
        "Cardápio",
        MODULE_BASE,
        [
            ("menu.view", "Ver cardápio", "Consultar produtos, categorias e adicionais."),
            ("menu.manage", "Gerenciar cardápio", "Criar e editar produtos, categorias e adicionais."),
        ],
    ),
    (
        "Cozinha (KDS)",
        MODULE_BASE,
        [
            ("kitchen.view", "Ver KDS", "Acompanhar os pedidos na cozinha."),
            ("kitchen.manage", "Operar KDS", "Avançar e concluir itens na cozinha."),
        ],
    ),
    (
        "Mesas & Comandas",
        MODULE_BASE,
        [
            ("tables.view", "Ver mesas e comandas", "Consultar o mapa de mesas e comandas."),
            ("tables.manage", "Gerenciar mesas e comandas", "Abrir, transferir e fechar mesas/comandas."),
        ],
    ),
    (
        "Clientes",
        MODULE_BASE,
        [
            ("customers.view", "Ver clientes", "Consultar a base de clientes."),
            ("customers.manage", "Gerenciar clientes", "Cadastrar e editar clientes."),
        ],
    ),
    (
        "Relatórios",
        MODULE_BASE,
        [
            ("reports.view.own", "Ver meus relatórios", "Relatórios das próprias vendas/operações."),
            ("reports.view", "Ver todos os relatórios", "Relatórios completos do restaurante/filial."),
        ],
    ),
    (
        "Equipe & Acesso",
        MODULE_BASE,
        [
            ("users.view", "Ver usuários", "Consultar a equipe."),
            ("users.manage", "Gerenciar usuários", "Convidar, editar e desativar usuários."),
            ("roles.manage", "Gerenciar perfis de acesso", "Criar e editar perfis (grupos de permissão)."),
        ],
    ),
    (
        "Equipamentos",
        MODULE_BASE,
        [
            ("devices.manage", "Impressoras e balanças", "Configurar impressoras e balanças."),
        ],
    ),
    # ── Módulos opcionais: mantidos para preservar códigos já em uso ──────────
    (
        "Estoque",
        "logistica",
        [
            ("stock.manage", "Gerenciar estoque", "Movimentar e ajustar o estoque."),
        ],
    ),
]


def iter_permissions():
    """Gera ``(code, defaults)`` prontos para ``update_or_create`` no upsert.

    ``defaults`` traz ``name``, ``description``, ``group``, ``module`` e um
    ``sort_order`` incremental (garante a ordem estável do catálogo).
    """
    sort = 0
    for group_label, module, items in PERMISSION_GROUPS:
        for code, name, description in items:
            sort += 1
            yield code, {
                "name": name,
                "description": description,
                "group": group_label,
                "module": module,
                "sort_order": sort,
            }


def codes_in_group(group_label):
    """Todos os códigos de um grupo (útil para semear perfis padrão)."""
    return [
        code
        for label, _module, items in PERMISSION_GROUPS
        if label == group_label
        for code, *_ in items
    ]


# Lista achatada de todos os códigos do catálogo, na ordem de exibição.
ALL_CODES = [code for _label, _module, items in PERMISSION_GROUPS for code, *_ in items]
