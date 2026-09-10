"""
Menus que todo site ganha de graça.

Um restaurante recém-criado não tem menu nenhum, e o editor ofereceria uma
lista vazia em todo bloco que pede um. O cliente teria de entender o conceito
de menu, criar um, escolher o tipo e a origem — tudo antes de conseguir ver um
carrossel na home. Estes quatro nascem prontos:

| menu                | origem              | serve a                        |
| ------------------- | ------------------- | ------------------------------ |
| Categorias          | todas as categorias | nav do topo, vitrine de chips  |
| Destaques           | mais vendidos (5)   | carrossel de produtos da home  |
| Ofertas             | em promoção         | faixa de ofertas               |
| Navegação principal | manual              | barra do cabeçalho             |

Os três primeiros são **dinâmicos**: respondem sozinhos e nunca ficam
desatualizados — criar uma categoria nova já a coloca no menu de categorias. O
de navegação nasce manual e vazio de propósito: links de topo são escolha
editorial, e adivinhar quais seriam daria um menu errado que alguém teria de
limpar.

Idempotente: roda de novo sem duplicar (a chave é o `slug` dentro da conta).
"""
from apps.menu.models import Menu

# `slug` é a chave de idempotência e o que os blocos usam para apontar para o
# menu — mudá-lo depois quebraria as páginas já montadas.
DEFAULT_MENUS = [
    {
        "slug": "categorias",
        "name": "Categorias",
        "menu_type": Menu.TYPE_SHOWCASE,
        "source": Menu.SOURCE_ALL_CATEGORIES,
        "item_limit": 0,
    },
    {
        "slug": "destaques",
        "name": "Destaques",
        "menu_type": Menu.TYPE_SHOWCASE,
        "source": Menu.SOURCE_BEST_SELLERS,
        "item_limit": 5,
    },
    {
        "slug": "ofertas",
        "name": "Ofertas",
        "menu_type": Menu.TYPE_SHOWCASE,
        "source": Menu.SOURCE_PROMOTIONS,
        "item_limit": 8,
    },
    {
        "slug": "navegacao-principal",
        "name": "Navegacao principal",
        "menu_type": Menu.TYPE_NAVIGATION,
        "source": Menu.SOURCE_MANUAL,
        "item_limit": 0,
    },
]


def ensure_default_menus(restaurant, *, user=None):
    """Cria os menus padrão do restaurante. Devolve os que existem ao final."""
    author = user if getattr(user, "is_authenticated", False) else None
    menus = []

    for spec in DEFAULT_MENUS:
        menu, _created = Menu.all_objects.get_or_create(
            account=restaurant.account,
            slug=spec["slug"],
            deleted_at__isnull=True,
            defaults={
                "restaurant": restaurant,
                "name": spec["name"],
                "menu_type": spec["menu_type"],
                "source": spec["source"],
                "item_limit": spec["item_limit"],
                "channel": Menu.CHANNEL_DIGITAL,
                "is_active": True,
                "created_by": author,
                "updated_by": author,
            },
        )
        menus.append(menu)

    return menus
