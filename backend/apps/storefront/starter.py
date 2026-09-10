"""
Página inicial padrão do storefront — e a biblioteca de seções reutilizáveis.

Um site que nasce em branco não é um site: o restaurante abre o editor, vê um
retângulo vazio e fecha. Todo site criado aqui já vem com a home montada e
publicada — faixa de aviso, cabeçalho com busca, capa promocional, categorias,
barra de filtros, vitrine com selo/nota/preço antigo e rodapé —, alimentada
pelos dados reais do restaurante.

As mesmas seções são exportadas em ``SECTION_LIBRARY`` para serem oferecidas
soltas no editor. É o ponto do arquivo: a home padrão não é um layout único e
fechado, é uma *composição* de seções que o cliente pode remover, reordenar e
tornar a inserir — e são exatamente as mesmas peças, não uma segunda versão que
vai divergir na primeira correção.

Duas escolhas sustentam tudo aqui:

- **Nenhuma cor literal.** Tudo é `var(--sf-*)`, que o renderer preenche a
  partir do tema (ver ``themes.py``). É o que permite trocar o preset e
  repintar a página inteira sem editar um bloco sequer.
- **Nenhum dado copiado.** Os blocos de vitrine guardam só configuração
  (`limit`, `columns`, `show_price`); nome, preço e foto do produto vêm da API
  pública na hora de renderizar. Um preço alterado no PDV aparece no site sem
  ninguém reabrir o editor.

A estrutura segue o padrão do builder: `wrapper > sf-section > sf-container >
componente`.
"""

CONTAINER_STYLE = {
    "width": "100%",
    "max-width": "var(--sf-container-width)",
    "margin": "0 auto",
    "padding": "0 24px",
}

# Respiro vertical das seções: 8px em cima e 8px embaixo.
#
# O número parece pequeno porque ele CONTA DUAS VEZES — o padding de baixo de
# uma seção encosta no de cima da seguinte, então 8px viram 16px de vazio entre
# duas seções. Com os 48px originais isso dava quase 100px, e a home parecia
# esticada: o visitante rolava por espaço em branco em vez de por produto.
# Loja de verdade encosta as seções; quem puxa o olho é a foto, não o vão.
SECTION_STYLE = {"padding": "8px 0", "background-color": "var(--sf-background)"}
SECTION_ALT_STYLE = {"padding": "8px 0", "background-color": "var(--sf-surface)"}


def _container(children, style=None):
    return {
        "type": "sf-container",
        "tagName": "div",
        "style": {**CONTAINER_STYLE, **(style or {})},
        "components": children,
    }


def _section(children, style=None, name=""):
    node = {
        "type": "sf-section",
        "tagName": "section",
        "style": {**SECTION_STYLE, **(style or {})},
        "components": [_container(children)],
    }
    if name:
        node["name"] = name
    return node


def _heading(text, level="h2", style=None):
    return {
        "type": "sf-heading",
        "tagName": level,
        "content": text,
        "style": {
            "font-family": "var(--sf-heading-font)",
            "font-size": "28px",
            "font-weight": "700",
            "color": "var(--sf-text)",
            "margin": "0 0 8px",
            **(style or {}),
        },
    }


def _text(text, style=None):
    return {
        "type": "sf-text",
        "tagName": "p",
        "content": text,
        "style": {
            "font-size": "16px",
            "line-height": "1.6",
            "color": "var(--sf-muted-text)",
            "margin": "0 0 24px",
            **(style or {}),
        },
    }


def _button(text, href="#cardapio", style=None):
    return {
        "type": "sf-button",
        "tagName": "a",
        "content": text,
        "attributes": {"href": href},
        "style": {
            "display": "inline-flex",
            "align-items": "center",
            "gap": "8px",
            "padding": "12px 24px",
            # Amarelo sobre verde: o botão é o elemento de maior contraste da
            # capa, e é ele que leva ao cardápio.
            "background-color": "var(--sf-accent)",
            "color": "var(--sf-secondary)",
            "font-weight": "700",
            "text-decoration": "none",
            "border-radius": "999px",
            **(style or {}),
        },
    }


# ── Seções reutilizáveis ─────────────────────────────────────────────────────
# Cada função devolve uma seção pronta. A home padrão é a lista delas; o editor
# oferece as mesmas peças no painel de blocos (ver `SECTION_LIBRARY`).


def section_announcement(text=""):
    """Faixa fina no topo: frete, prazo, cupom."""
    return {
        "type": "sf-announcement-bar",
        "name": "Faixa de aviso",
        "props": {
            "message": text or "Peça pelo site e receba em casa · Retirada no balcão sem fila",
            "dismissible": False,
        },
        "style": {
            "padding": "10px 24px",
            "background-color": "var(--sf-secondary)",
            "color": "var(--sf-background)",
            "font-size": "13px",
            "text-align": "center",
        },
    }


def default_header(restaurant_name="", nav_menu="categorias"):
    """Configuração do cabeçalho — vive no SITE, não na página.

    O cabeçalho aparece em todas as páginas e não pode ser apagado por engano
    no editor; por isso é `MenuSite.header` e não um bloco. A navegação aponta
    para um MENU pelo handle, então o restaurante monta a lista uma vez (com
    submenus) e a reaproveita onde quiser.

    O padrão é o menu de CATEGORIAS, e não o de navegação: o de navegação nasce
    manual e vazio (links de topo são escolha editorial, e adivinhá-los daria
    uma barra errada), então apontar para ele deixaria o site novo sem o
    terceiro nível do cabeçalho. As categorias são dinâmicas e verdadeiras
    desde o primeiro minuto — e o cliente troca por `navegacao-principal`
    quando tiver os links dele.
    """
    return {
        "sticky": True,
        "brand_name": restaurant_name,
        "logo_url": "",
        "announcement": {
            "enabled": True,
            "text": "Peça pelo site e receba em casa",
            "highlight": "Frete grátis",
            "secondary": "Retirada no balcão sem fila",
            "url": "",
        },
        "location": {"enabled": True, "label": "Entregar em", "value": ""},
        "search": {"enabled": True, "placeholder": "Buscar produtos e categorias"},
        "actions": {
            "cart": True,
            "profile": True,
            # `icon`: só o círculo colorido. `icon_text` põe o rótulo ao lado;
            # `text` tira o ícone e deixa só a palavra.
            "display": "icon",
            "cart_label": "Carrinho",
            "profile_label": "Entrar",
        },
        "nav_menu": nav_menu,
        "secondary_menu": "",
    }


def section_hero(title="", subtitle="", highlight=""):
    """Capa promocional: bloco verde, chamada grande e botão amarelo.

    É um bloco de CONFIGURAÇÃO, não um contêiner com filhos: título, destaque,
    descrição, botão, imagem e medidas são props, e o editor os expõe como
    campos. A alternativa (montar a capa com um título, um texto e um botão
    soltos dentro) parece mais flexível, mas quebra fácil — arrastar o botão
    para fora deixa uma capa sem chamada para ação, e é o cliente que descobre
    isso depois de publicar.

    As medidas têm variante por dispositivo (`_tablet`, `_mobile`) porque a
    mesma capa que respira em 1360px sufoca em 375px: no celular o texto vai
    para cima da imagem, e não ao lado.
    """
    return {
        "type": "sf-hero",
        "name": "Capa promocional",
        "props": {
            "title": title or "Peça hoje e receba em casa",
            # Trecho em amarelo dentro do título — o gancho da campanha. É prop
            # separada, e não `<em>` dentro do título: o bloco renderiza texto
            # puro, e HTML no meio sairia escapado na tela.
            "highlight": highlight or "sem taxa",
            "description": subtitle or "Produtos fresquinhos, escolhidos na hora e entregues na sua porta.",
            "cta_label": "Ver cardápio",
            "cta_url": "#cardapio",
            "image": "",
            "image_position": "right-bottom",
            "image_width": "52%",
            "height": "350px",
            "height_tablet": "300px",
            "height_mobile": "520px",
            "align": "left",
            "align_mobile": "center",
            "padding": "56px",
            "padding_mobile": "32px",
            "background": "",
            "decorations": True,
        },
        "style": {
            "margin": "20px auto 0",
            "max-width": "var(--sf-container-width)",
        },
    }


def section_categories():
    """Categorias em chips, logo abaixo da capa."""
    return _section(
        [
            _heading("Categorias"),
            _text("Escolha por onde começar."),
            {"type": "sf-categories", "props": {"layout": "chips", "show_all": True}},
        ],
        name="Categorias",
    )


def section_product_grid(title="Todos os produtos", subtitle="", alt=False):
    """Vitrine completa: filtros em cima, cartões com selo, nota e preço."""
    return _section(
        [
            _heading(title),
            _text(subtitle or "Tudo o que está disponível hoje."),
            {
                "type": "sf-filter-bar",
                "props": {
                    "show_categories": True,
                    "show_sort": True,
                    "sort_options": ["default", "price_asc", "price_desc", "name"],
                },
                "style": {"margin": "0 0 24px"},
            },
            {
                "type": "sf-product-grid",
                "props": {
                    "category_id": None,
                    "columns": {"desktop": 4, "tablet": 2, "mobile": 2},
                    "show_image": True,
                    "show_description": False,
                    "show_price": True,
                    "show_old_price": True,
                    "show_button": True,
                    "show_badges": True,
                    "show_rating": True,
                    "card_style": "market",
                    "sort": "default",
                },
            },
        ],
        style=SECTION_ALT_STYLE if alt else SECTION_STYLE,
        name="Vitrine de produtos",
    )


def section_featured_carousel():
    """Destaques em carrossel, com setas para o lado.

    A curadoria vem do menu `destaques`, que `ensure_default_menus` cria em
    toda conta como "mais vendidos" — dinâmico, então a faixa se atualiza
    sozinha e nunca estreia vazia num restaurante que já vende. Apontar para o
    menu, e não para um filtro solto, é o que permite ao restaurante trocar o
    critério depois (escolher os produtos a dedo, por exemplo) sem tocar na
    página.
    """
    return _section(
        [
            _heading("Destaques da casa"),
            _text("Os mais pedidos, em um passe de olho."),
            {
                "type": "sf-product-carousel",
                "props": {
                    "menu": "destaques",
                    "layout": "carousel",
                    "columns": {"desktop": 4, "tablet": 2, "mobile": 2},
                    "show_image": True,
                    "show_price": True,
                    "show_old_price": True,
                    "show_button": True,
                    "show_badges": True,
                    "show_rating": True,
                    "card_style": "market",
                },
            },
        ],
        name="Destaques",
    )


def section_promotions():
    """Faixa de promoções: só o que tem preço promocional."""
    return _section(
        [
            _heading("Ofertas do dia"),
            _text("Preço promocional enquanto durar o estoque."),
            {
                "type": "sf-promotions",
                "props": {
                    "limit": 4,
                    "columns": {"desktop": 4, "tablet": 2, "mobile": 2},
                    "show_badges": True,
                    "show_old_price": True,
                    "show_rating": True,
                    "card_style": "market",
                },
            },
        ],
        style=SECTION_ALT_STYLE,
        name="Ofertas",
    )


def section_info():
    """Horários, endereço e formas de pagamento."""
    return _section(
        [
            _heading("Horários e endereço"),
            {
                "type": "sf-opening-hours",
                "props": {"layout": "list", "highlight_today": True},
                "style": {"margin": "0 0 32px"},
            },
            {
                "type": "sf-restaurant-info",
                "props": {"show_map": False, "show_phone": True, "show_address": True},
                "style": {"margin": "0 0 24px"},
            },
            {"type": "sf-payment-methods", "props": {}},
        ],
        name="Informações",
    )


def section_footer():
    """Rodapé: identificação, duas colunas de links e formas de pagamento.

    As duas primeiras colunas ficam vazias por padrão (`link_menu_1`/
    `link_menu_2` sem slug): o site novo não tem página de política ou termos
    ainda, e uma coluna sem menu simplesmente some (ver `SfFooter.vue`). Quando
    o restaurante criar um menu manual com esses links, basta apontar a coluna
    para o slug dele.

    A terceira já nasce apontada para `categorias`, que `ensure_default_menus`
    garante em toda conta e que se mantém sozinho: o rodapé estreia com o
    cardápio navegável em vez de só a linha de formas de pagamento.
    """
    return {
        "type": "sf-footer",
        "name": "Rodapé",
        "props": {
            "show_social": True,
            "show_payment_methods": True,
            "link_menu_1_title": "Institucional",
            "link_menu_1": "",
            "link_menu_2_title": "Atendimento",
            "link_menu_2": "",
            "link_menu_3_title": "Cardápio",
            "link_menu_3": "categorias",
        },
        "style": {
            "padding": "48px 24px",
            "background-color": "var(--sf-secondary)",
            "color": "var(--sf-background)",
        },
    }


def section_whatsapp():
    return {
        "type": "sf-whatsapp-button",
        "name": "Botão de WhatsApp",
        "props": {"position": "floating"},
    }


# Nome exibido no editor → seção pronta. É esta lista que o painel de blocos do
# editor consome (via `GET /api/v1/storefront/schema/`) para oferecer as mesmas
# peças da home padrão como blocos arrastáveis.
SECTION_LIBRARY = [
    {"key": "hero", "label": "Capa promocional", "build": section_hero},
    {"key": "categories", "label": "Categorias", "build": section_categories},
    {"key": "featured-carousel", "label": "Destaques em carrossel", "build": section_featured_carousel},
    {"key": "product-grid", "label": "Vitrine de produtos", "build": section_product_grid},
    {"key": "promotions", "label": "Ofertas do dia", "build": section_promotions},
    {"key": "info", "label": "Horários e endereço", "build": section_info},
    {"key": "footer", "label": "Rodapé", "build": section_footer},
    {"key": "whatsapp", "label": "Botão de WhatsApp", "build": section_whatsapp},
]


def section_presets():
    """`[{key, label, component}]` — as seções prontas, já montadas."""
    return [{"key": item["key"], "label": item["label"], "component": item["build"]()} for item in SECTION_LIBRARY]


def build_starter_page(restaurant_name="", tagline=""):
    """Árvore de blocos da home padrão, já com o nome do restaurante no lugar."""
    title = restaurant_name or "Bem-vindo"
    subtitle = tagline or "Peça online: escolha no cardápio, receba em casa ou retire no balcão."

    return {
        "pages": [
            {
                "name": "Home",
                "frames": [
                    {
                        "component": {
                            "type": "wrapper",
                            "components": [
                                # Sem faixa e sem cabeçalho aqui: os dois são
                                # do SITE (`MenuSite.header`), renderizados em
                                # todas as páginas e fora do alcance de uma
                                # exclusão acidental no editor.
                                section_hero(
                                    "Bem-vindo à" if restaurant_name else title,
                                    subtitle,
                                    highlight=restaurant_name,
                                ),
                                section_categories(),
                                section_featured_carousel(),
                                section_promotions(),
                                section_product_grid(),
                                section_info(),
                                section_footer(),
                                section_whatsapp(),
                            ],
                        }
                    }
                ],
            }
        ],
        "styles": [],
        "assets": [],
    }


def starter_seo(restaurant_name=""):
    name = restaurant_name or "Cardápio digital"
    return {
        "title": name,
        "description": f"Peça online no {name}: cardápio completo, entrega e retirada.",
        "index": True,
    }
