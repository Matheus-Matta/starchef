"""Cria o site de quem ainda não tem, com tema e home padrão (idempotente).

    python manage.py provision_storefronts
    python manage.py provision_storefronts --account <id> --theme dark
    python manage.py provision_storefronts --all-accounts --dry-run

Restaurantes cadastrados ANTES de o módulo E-commerce ser habilitado não
passaram pelo sinal de provisionamento e ficariam sem site. Este comando fecha
essa lacuna — e serve como o caminho manual quando alguém quer o cardápio de
uma conta específica no ar sem esperar ninguém abrir o painel.

Por padrão só toca em contas com o módulo E-commerce habilitado; `--all-accounts`
ignora essa checagem (útil ao preparar uma conta antes da venda do módulo).
"""
from django.core.management.base import BaseCommand

from apps.restaurants.models import Restaurant
from apps.storefront.services.provisioning import account_has_storefront, ensure_site
from apps.storefront.themes import DEFAULT_THEME_KEY, THEME_PRESET_KEYS


class Command(BaseCommand):
    help = "Provisiona o site do storefront (tema + home publicada) para os restaurantes que ainda não têm."

    def add_arguments(self, parser):
        parser.add_argument("--account", help="Provisiona apenas os restaurantes desta conta.")
        parser.add_argument("--restaurant", help="Provisiona apenas este restaurante.")
        parser.add_argument(
            "--theme",
            default=DEFAULT_THEME_KEY,
            choices=THEME_PRESET_KEYS,
            help=f"Tema inicial aplicado (default: {DEFAULT_THEME_KEY}).",
        )
        parser.add_argument(
            "--all-accounts",
            action="store_true",
            help="Inclui contas sem o módulo E-commerce habilitado.",
        )
        parser.add_argument(
            "--draft",
            action="store_true",
            help="Cria a home como rascunho em vez de publicá-la.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Só lista o que seria feito.")

    def handle(self, *args, **options):
        queryset = Restaurant.all_objects.filter(deleted_at__isnull=True).select_related("account")
        if options["account"]:
            queryset = queryset.filter(account_id=options["account"])
        if options["restaurant"]:
            queryset = queryset.filter(id=options["restaurant"])

        provisioned = skipped = 0
        for restaurant in queryset.order_by("trade_name"):
            if not options["all_accounts"] and not account_has_storefront(restaurant.account):
                skipped += 1
                continue

            if options["dry_run"]:
                self.stdout.write(f"[dry-run] {restaurant.trade_name} ({restaurant.account.name})")
                provisioned += 1
                continue

            site = ensure_site(restaurant, theme_key=options["theme"], publish=not options["draft"])
            provisioned += 1
            self.stdout.write(f"{restaurant.trade_name} -> /{site.slug}/")

        self.stdout.write(
            self.style.SUCCESS(
                f"Storefronts provisionados: {provisioned}. Ignorados (sem o módulo E-commerce): {skipped}."
            )
        )
