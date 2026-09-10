"""Semeia o catálogo de modelos de página da plataforma (idempotente).

    python manage.py seed_storefront_templates

Os modelos são conteúdo da PLATAFORMA, não de nenhuma conta: quando aplicados
a uma página, o conteúdo é copiado e o vínculo se desfaz (ver
``services.publishing.apply_template``). Por isso podem ser reescritos por este
comando a qualquer momento sem afetar nenhum site já montado.

Cada modelo passa pelo mesmo validador do editor antes de ser gravado — se um
modelo do catálogo trouxesse um bloco proibido, ele só falharia na hora em que
um cliente tentasse aplicá-lo.
"""
from django.core.management.base import BaseCommand

from apps.storefront.builder_schema import BuilderValidationError, validate_project_data
from apps.storefront.models import MenuTemplate


def _section(children, style=None):
    return {
        "type": "sf-section",
        "tagName": "section",
        "style": style or {"padding": "64px 24px"},
        "components": children,
    }


def _heading(text, style=None):
    return {"type": "sf-heading", "tagName": "h1", "content": text, "style": style or {"font-size": "42px"}}


def _text(text, style=None):
    return {"type": "sf-text", "tagName": "p", "content": text, "style": style or {"font-size": "18px"}}


def _button(text, href="#cardapio", style=None):
    return {
        "type": "sf-button",
        "tagName": "a",
        "content": text,
        "attributes": {"href": href},
        "style": style or {"display": "inline-block", "padding": "14px 28px", "border-radius": "999px"},
    }


def _grid(props, style=None):
    return {"type": "sf-product-grid", "props": props, "style": style or {"padding": "0 24px 64px"}}


def _project(components):
    return {"pages": [{"name": "Home", "frames": [{"component": {"type": "wrapper", "components": components}}]}]}


TEMPLATES = [
    {
        "slug": "pizzaria-moderna",
        "name": "Pizzaria Moderna",
        "category": "Pizzaria",
        "description": "Hero com foto grande, vitrine em 4 colunas e horário de funcionamento.",
        "sort_order": 10,
        "project_data": _project(
            [
                {
                    "type": "sf-hero",
                    "props": {"align": "center", "height": "large"},
                    "style": {"background-color": "#111111", "color": "#ffffff", "padding": "96px 24px"},
                    "components": [
                        _heading("A pizza que o bairro espera", {"font-size": "48px", "text-align": "center"}),
                        _text("Massa de fermentação natural, forno a lenha.", {"text-align": "center"}),
                        _button("Ver cardápio", style={"background-color": "#E53935", "color": "#fff", "padding": "14px 28px", "border-radius": "999px"}),
                    ],
                },
                {"type": "sf-categories", "props": {"layout": "chips"}, "style": {"padding": "32px 24px"}},
                _grid({"columns": {"desktop": 4, "tablet": 2, "mobile": 1}, "show_description": True}),
                {"type": "sf-opening-hours", "props": {"layout": "table"}, "style": {"padding": "48px 24px"}},
                {"type": "sf-footer", "props": {"show_social": True}, "style": {"padding": "40px 24px", "background-color": "#111111", "color": "#ffffff"}},
            ]
        ),
    },
    {
        "slug": "hamburgueria-dark",
        "name": "Hamburgueria Dark",
        "category": "Hamburgueria",
        "description": "Tema escuro, destaque para promoções e botão de WhatsApp.",
        "sort_order": 20,
        "project_data": _project(
            [
                {
                    "type": "sf-banner",
                    "props": {"variant": "full"},
                    "style": {"background-color": "#0d0d0d", "color": "#f5f5f5", "padding": "80px 24px"},
                    "components": [_heading("Smash burgers todo dia", {"font-size": "44px"})],
                },
                {"type": "sf-promotions", "props": {"limit": 4}, "style": {"padding": "48px 24px"}},
                _grid({"columns": {"desktop": 3, "tablet": 2, "mobile": 1}, "show_description": False}),
                {"type": "sf-whatsapp-button", "props": {"position": "floating"}},
                {"type": "sf-footer", "props": {"show_social": True}, "style": {"padding": "40px 24px"}},
            ]
        ),
    },
    {
        "slug": "minimalista",
        "name": "Minimalista",
        "category": "Geral",
        "description": "Só o essencial: título, categorias e a lista de produtos.",
        "sort_order": 30,
        "project_data": _project(
            [
                _section([_heading("Cardápio"), _text("Escolha, peça e retire ou receba em casa.")]),
                {"type": "sf-categories", "props": {"layout": "list"}, "style": {"padding": "0 24px"}},
                _grid({"columns": {"desktop": 2, "tablet": 2, "mobile": 1}, "show_description": True}),
                {"type": "sf-restaurant-info", "props": {"show_map": False}, "style": {"padding": "48px 24px"}},
            ]
        ),
    },
    {
        "slug": "cafeteria",
        "name": "Cafeteria",
        "category": "Cafeteria",
        "description": "Clima acolhedor, destaques da casa e informações da loja.",
        "sort_order": 40,
        "project_data": _project(
            [
                {
                    "type": "sf-hero",
                    "props": {"align": "left"},
                    "style": {"background-color": "#F6F1EA", "padding": "80px 24px"},
                    "components": [
                        _heading("Café fresco, todo dia", {"font-size": "40px"}),
                        _button("Fazer pedido"),
                    ],
                },
                {"type": "sf-featured-products", "props": {"limit": 6}, "style": {"padding": "48px 24px"}},
                _grid({"columns": {"desktop": 3, "tablet": 2, "mobile": 1}, "show_description": True}),
                {"type": "sf-opening-hours", "props": {"layout": "list"}, "style": {"padding": "32px 24px"}},
                {"type": "sf-restaurant-info", "props": {"show_map": True}, "style": {"padding": "0 24px 64px"}},
            ]
        ),
    },
    {
        "slug": "confeitaria",
        "name": "Confeitaria",
        "category": "Confeitaria",
        "description": "Vitrine em destaque, promoções e formas de pagamento.",
        "sort_order": 50,
        "project_data": _project(
            [
                {
                    "type": "sf-banner",
                    "props": {"variant": "soft"},
                    "style": {"background-color": "#FFF0F5", "padding": "72px 24px"},
                    "components": [_heading("Doces feitos na hora", {"font-size": "40px", "text-align": "center"})],
                },
                {"type": "sf-product-carousel", "props": {"limit": 8}, "style": {"padding": "32px 0"}},
                _grid({"columns": {"desktop": 4, "tablet": 2, "mobile": 2}, "show_description": False}),
                {"type": "sf-payment-methods", "props": {}, "style": {"padding": "32px 24px"}},
                {"type": "sf-footer", "props": {"show_social": True}, "style": {"padding": "40px 24px"}},
            ]
        ),
    },
]


class Command(BaseCommand):
    help = "Semeia/atualiza os modelos de página do storefront (idempotente)."

    def handle(self, *args, **options):
        created = updated = 0
        for spec in TEMPLATES:
            try:
                project_data = validate_project_data(spec["project_data"])
            except BuilderValidationError as exc:
                self.stderr.write(self.style.ERROR(f"Modelo '{spec['slug']}' inválido: {exc.errors}"))
                continue

            _template, was_created = MenuTemplate.objects.update_or_create(
                slug=spec["slug"],
                defaults={
                    "name": spec["name"],
                    "description": spec["description"],
                    "category": spec["category"],
                    "sort_order": spec["sort_order"],
                    "project_data": project_data,
                    "is_active": True,
                },
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(self.style.SUCCESS(f"Modelos do storefront: {created} criados, {updated} atualizados."))
