from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from django.db import connection
from django.db.migrations.exceptions import InconsistentMigrationHistory
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.core.management.commands._demo_seed import (
    DEFAULT_ACCOUNT_NAME,
    DEFAULT_ACCOUNT_SLUG,
    DEFAULT_BRANCH_NAME,
    DEFAULT_EMAIL,
    DEFAULT_PASSWORD,
    DEFAULT_RESTAURANT_NAME,
    DEFAULT_USERNAME,
    ensure_base_tenant,
    ensure_demo_roles,
    ensure_restaurant_in_account,
    ensure_tenant_user,
)
from apps.core.tenant import tenant_context
from apps.customers.models import Customer, CustomerAddress
from apps.menu.models import (
    Ingredient,
    Menu,
    MenuItem,
    Product,
    ProductAddon,
    ProductCategory,
    ProductVariation,
    Recipe,
    RecipeItem,
)
from apps.orders.models import Order, OrderItem
from apps.orders.services import add_order_item, close_order, create_order, send_order_to_kitchen
from apps.payments.models import CashMovement, CashRegister, CashStation, Payment, PaymentMethod
from apps.payments.services import open_cash_register, register_payment
from apps.invoices.models import FiscalConfig, FiscalProfile
from apps.printers.models import Printer, Scale
from apps.restaurants.models import Deliveryman, DeliveryZone, Table, TableSector
from apps.stock.models import StockLocation, StockMovement


class Command(BaseCommand):
    help = "Seed two demo tenants with rich data: Burger Palace (2 restaurantes) + Bella Trattoria (tenant isolado)."

    def add_arguments(self, parser):
        parser.add_argument("--account-slug", default=DEFAULT_ACCOUNT_SLUG)
        parser.add_argument("--account-name", default=DEFAULT_ACCOUNT_NAME)
        parser.add_argument("--restaurant-name", default=DEFAULT_RESTAURANT_NAME)
        parser.add_argument("--branch-name", default=DEFAULT_BRANCH_NAME)
        parser.add_argument("--username", default=DEFAULT_USERNAME)
        parser.add_argument("--email", default=DEFAULT_EMAIL)
        parser.add_argument("--password", default=DEFAULT_PASSWORD)
        parser.add_argument("--skip-orders", action="store_true")
        parser.add_argument("--skip-tenant-2", action="store_true", help="Pula a criação do segundo tenant.")
        parser.add_argument("--migrate", action="store_true", help="Roda migrations antes do seed.")
        parser.add_argument(
            "--reset-sqlite",
            action="store_true",
            help="Faz backup e recria o banco SQLite antes das migrations.",
        )

    def handle(self, *args, **options):
        if options["reset_sqlite"]:
            self._reset_sqlite_database()
            options["migrate"] = True

        if options["migrate"]:
            self.stdout.write(self.style.NOTICE("Rodando migrations..."))
            try:
                call_command("migrate", verbosity=options["verbosity"])
            except InconsistentMigrationHistory as exc:
                raise CommandError(
                    f"{exc}\n\n"
                    "Histórico de migrations inconsistente. Use: python manage.py seed_demo --reset-sqlite"
                ) from exc

        # ── TENANT 1: Burger Palace (2 restaurantes para testar separação) ────
        self.stdout.write(self.style.NOTICE("Seeding Tenant 1: Burger Palace / Pizza Rustica..."))

        account, r1, b1 = ensure_base_tenant(
            account_slug=options["account_slug"],
            account_name=options["account_name"],
            restaurant_name=options["restaurant_name"],
            branch_name=options["branch_name"],
            restaurant_city="São Paulo",
            restaurant_state="SP",
            restaurant_address="Av. Atlântica, 500",
            restaurant_phone="(21) 3000-0100",
            restaurant_email="contato@burgerpalace.test",
        )
        roles = ensure_demo_roles(account, r1)

        admin = ensure_tenant_user(
            account=account,
            username=options["username"],
            email=options["email"],
            password=options["password"],
            first_name="Admin",
            last_name="StarChef",
            profile_type=UserProfile.PROFILE_ADMIN,
            restaurant=r1,
            branch=b1,
            role=roles["admin"],
            is_staff=True,
            is_superuser=True,
        )
        garcom1 = ensure_tenant_user(
            account=account,
            username="garcom.joao",
            email="joao@burgerpalace.test",
            password=DEFAULT_PASSWORD,
            first_name="João",
            last_name="Ferreira",
            profile_type=UserProfile.PROFILE_WAITER,
            restaurant=r1,
            branch=b1,
            role=roles["waiter"],
            phone="(21) 90001-0001",
        )
        caixa1 = ensure_tenant_user(
            account=account,
            username="caixa.maria",
            email="maria@burgerpalace.test",
            password=DEFAULT_PASSWORD,
            first_name="Maria",
            last_name="Santos",
            profile_type=UserProfile.PROFILE_CASHIER,
            restaurant=r1,
            branch=b1,
            role=roles["cashier"],
            phone="(21) 90001-0002",
        )
        ensure_tenant_user(
            account=account,
            username="cozinha.carlos",
            email="carlos@burgerpalace.test",
            password=DEFAULT_PASSWORD,
            first_name="Carlos",
            last_name="Alves",
            profile_type=UserProfile.PROFILE_KITCHEN,
            restaurant=r1,
            branch=b1,
            role=roles["kitchen"],
            phone="(21) 90001-0003",
        )

        # Segundo restaurante no mesmo tenant para testar separação de dados
        r2, b2 = ensure_restaurant_in_account(
            account,
            restaurant_name="Pizza Rustica",
            branch_name="Botafogo",
            cnpj_seed=f"{options['account_slug']}-pizza-rustica",
            city="Rio de Janeiro",
            state="RJ",
            address="Rua Voluntários da Pátria, 200",
            phone="(21) 3000-0200",
            email="contato@pizzarustica.test",
        )
        gerente2 = ensure_tenant_user(
            account=account,
            username="gerente.pizzarustica",
            email="gerente@pizzarustica.test",
            password=DEFAULT_PASSWORD,
            first_name="Roberta",
            last_name="Lima",
            profile_type=UserProfile.PROFILE_MANAGER,
            restaurant=r2,
            branch=b2,
            role=roles["manager"],
            phone="(21) 90002-0001",
        )

        with tenant_context(account):
            self._seed_burger_palace(account, r1, b1, admin, garcom1, caixa1, skip_orders=options["skip_orders"])
            self._seed_pizza_rustica(account, r2, b2, gerente2, skip_orders=options["skip_orders"])

        self.stdout.write(self.style.SUCCESS("Tenant 1 pronto."))
        self.stdout.write(f"  conta: {account.slug}  |  admin: {admin.username} / {options['password']}")
        self.stdout.write(f"  rest1: {r1.trade_name} / {b1.name}  |  garcom: {garcom1.username}  |  caixa: {caixa1.username}")
        self.stdout.write(f"  rest2: {r2.trade_name} / {b2.name}  |  gerente: {gerente2.username}")

        # ── TENANT 2: Bella Trattoria (tenant totalmente isolado) ─────────────
        if not options["skip_tenant_2"]:
            self.stdout.write(self.style.NOTICE("Seeding Tenant 2: Bella Trattoria..."))
            account2, r3, b3 = ensure_base_tenant(
                account_slug="bella-trattoria-demo",
                account_name="Bella Trattoria",
                restaurant_name="Bella Trattoria",
                branch_name="Ipanema",
                restaurant_city="Rio de Janeiro",
                restaurant_state="RJ",
                restaurant_address="Rua Visconde de Pirajá, 300",
                restaurant_phone="(21) 3000-0300",
                restaurant_email="contato@bellatrattoria.test",
            )
            roles2 = ensure_demo_roles(account2, r3)
            owner2 = ensure_tenant_user(
                account=account2,
                username="owner.trattoria",
                email="owner@bellatrattoria.test",
                password="trattoria123",
                first_name="Marco",
                last_name="Rossi",
                profile_type=UserProfile.PROFILE_OWNER,
                restaurant=r3,
                branch=b3,
                role=roles2["owner"],
                is_staff=True,
            )
            with tenant_context(account2):
                self._seed_bella_trattoria(account2, r3, b3, owner2, skip_orders=options["skip_orders"])

            self.stdout.write(self.style.SUCCESS("Tenant 2 pronto."))
            self.stdout.write(f"  conta: {account2.slug}  |  owner: {owner2.username} / trattoria123")
            self.stdout.write(f"  rest: {r3.trade_name} / {b3.name}")

    # ═══════════════════════════════════════════════════════════════════════════
    # TENANT 1 — Restaurante 1: Burger Palace (Copacabana)
    # ═══════════════════════════════════════════════════════════════════════════

    def _seed_burger_palace(self, account, restaurant, branch, admin, garcom, caixa, *, skip_orders):
        u = admin
        sectors, tables = self._seed_tables_burger(account, restaurant, branch, u)
        pms = self._seed_payment_methods(account, restaurant, branch, u)
        stock_loc = self._seed_stock_location(account, restaurant, branch, u, "Estoque Burger Palace")
        self._seed_printers_burger(account, restaurant, branch, u)
        self._seed_delivery_zones_burger(account, restaurant, branch, u)
        self._seed_deliverymen_burger(account, restaurant, branch, u)
        cats = self._seed_categories_burger(account, restaurant, branch, u)
        ingrs = self._seed_ingredients_burger(account, restaurant, branch, u)
        prods = self._seed_products_burger(account, restaurant, branch, cats, u)
        # Balanca depende do produto por kilo e da impressora, entao vem apos os produtos.
        self._seed_scales_burger(account, restaurant, branch, prods, u)
        self._seed_fiscal_burger(account, restaurant, branch, u)
        self._seed_addons_burger(account, restaurant, branch, prods, u)
        self._seed_variations_burger(account, restaurant, branch, prods, u)
        self._seed_recipes_burger(account, restaurant, branch, prods, ingrs, u)
        self._seed_menus_burger(account, restaurant, branch, prods, u)
        customers = self._seed_customers_burger(account, restaurant, branch, u)
        self._seed_stock_movements(account, restaurant, branch, ingrs, stock_loc, u)
        if not skip_orders:
            cash_register = self._seed_cash_register(branch, caixa, extra_operators=[admin])
            self._seed_orders_burger(branch, tables, prods, customers, pms, admin, garcom, caixa)
            self._seed_current_cash_movements(cash_register, caixa)

    def _seed_tables_burger(self, account, restaurant, branch, user):
        sectors = {
            "salao": self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Salão"}, {"display_order": 1, "is_active": True, "created_by": user, "updated_by": user}),
            "varanda": self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Varanda"}, {"display_order": 2, "is_active": True, "created_by": user, "updated_by": user}),
            "vip": self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "VIP"}, {"display_order": 3, "is_active": True, "created_by": user, "updated_by": user}),
        }
        tables = {}
        for n in range(1, 11):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sectors["salao"], "capacity": 4, "is_active": True, "created_by": user, "updated_by": user})
        for n in range(11, 15):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sectors["varanda"], "capacity": 2, "is_active": True, "created_by": user, "updated_by": user})
        for n in range(15, 17):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sectors["vip"], "capacity": 6, "is_active": True, "created_by": user, "updated_by": user})
        return sectors, tables

    def _seed_printers_burger(self, account, restaurant, branch, user):
        # sector agora é FK opcional a TableSector — o demo deixa sem setor.
        for name, sector, auto in [("Cozinha", None, True), ("Bar", None, True), ("Caixa", None, False)]:
            self._upsert(Printer, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"sector": sector, "driver_type": Printer.DRIVER_BROWSER, "endpoint": "", "auto_print": auto, "is_active": True, "settings": {"demo": True}, "created_by": user, "updated_by": user})

    def _seed_scales_burger(self, account, restaurant, branch, prods, user):
        caixa_printer = Printer.objects.filter(account=account, branch=branch, name="Caixa").first()
        self._upsert(
            Scale,
            {"account": account, "restaurant": restaurant, "branch": branch, "name": "Balança Caixa"},
            {
                "protocol": Scale.PROTOCOL_TOLEDO_PRT2,
                "port": "COM3",
                "reading_max_age_seconds": 120,
                # Preço/kg vem do produto por kilo; nota sai na impressora do caixa.
                "product": prods.get("BP-KILO"),
                "printer": caixa_printer,
                "auto_print": False,
                "auto_print_delay_seconds": 3,
                "is_active": True,
                "settings": {"demo": True, "baudrate": 9600},
                "created_by": user,
                "updated_by": user,
            },
        )

    def _seed_fiscal_burger(self, account, restaurant, branch, user):
        # Perfil tributario padrao (Simples Nacional, aliquotas zeradas — configure depois).
        profile = self._upsert(
            FiscalProfile,
            {"account": account, "restaurant": restaurant, "branch": branch, "name": "Alimentacao - Simples Nacional"},
            {
                "ncm": "21069090", "cfop": "5102", "origem": "0", "csosn": "102",
                "icms_rate": Decimal("0"), "pis_rate": Decimal("0"), "cofins_rate": Decimal("0"),
                "approx_tax_rate": Decimal("0"), "is_default": True, "is_active": True,
                "created_by": user, "updated_by": user,
            },
        )
        # Config fiscal da filial em HOMOLOGACAO. CSC/certificado ficam EM BRANCO de proposito.
        self._upsert(
            FiscalConfig,
            {"account": account, "restaurant": restaurant, "branch": branch},
            {
                "provider": FiscalConfig.PROVIDER_MANUAL,
                "document_model": FiscalConfig.MODEL_NFCE,
                "environment": FiscalConfig.ENV_HOMOLOGATION,
                "crt": FiscalConfig.CRT_SIMPLES,
                "series": 1, "next_number": 1,
                "cnpj": "12.345.678/0001-90", "ie": "", "corporate_name": "Burger Palace Alimentos LTDA",
                "trade_name": "Burger Palace", "address_line": "Av. Atlantica, 1000",
                "city": "Rio de Janeiro", "uf": "RJ", "city_ibge": "3304557", "zip_code": "22010-000",
                "csc_id": "", "csc_token": "", "qr_base_url": "", "portal_url": "https://www.nfce.fazenda.rj.gov.br",
                "certificate_ref": "", "default_profile": profile, "is_active": True,
                "created_by": user, "updated_by": user,
            },
        )

    def _seed_delivery_zones_burger(self, account, restaurant, branch, user):
        zones = [
            ("Centro (0-3km)", "0", "3", "5.00", 30),
            ("Zona Sul (3-6km)", "3", "6", "8.00", 45),
            ("Arredores (6-10km)", "6", "10", "12.00", 60),
        ]
        for name, r_min, r_max, fee, minutes in zones:
            self._upsert(
                DeliveryZone,
                {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
                {"min_radius_km": Decimal(r_min), "max_radius_km": Decimal(r_max), "delivery_fee": Decimal(fee), "estimated_minutes": minutes, "is_active": True, "created_by": user, "updated_by": user},
            )

    def _seed_deliverymen_burger(self, account, restaurant, branch, user):
        deliverymen = [
            ("Carlos Silva", "(21) 98001-0001", Deliveryman.VEHICLE_MOTORCYCLE, "RIO-0001"),
            ("Diego Pereira", "(21) 98001-0002", Deliveryman.VEHICLE_MOTORCYCLE, "RIO-0002"),
            ("Fernanda Costa", "(21) 98001-0003", Deliveryman.VEHICLE_BIKE, ""),
        ]
        for name, phone, vehicle, plate in deliverymen:
            self._upsert(
                Deliveryman,
                {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
                {"phone": phone, "vehicle_type": vehicle, "vehicle_plate": plate, "is_active": True, "created_by": user, "updated_by": user},
            )

    def _seed_categories_burger(self, account, restaurant, branch, user):
        cats = [("Burgers", 1), ("Acompanhamentos", 2), ("Bebidas", 3), ("Sobremesas", 4), ("Combos", 5), ("Self-service", 6)]
        return {name: self._upsert(ProductCategory, {"account": account, "restaurant": restaurant, "branch": branch, "name": name, "parent": None}, {"display_order": order, "is_active": True, "created_by": user, "updated_by": user}) for name, order in cats}

    def _seed_ingredients_burger(self, account, restaurant, branch, user):
        data = [
            ("Pão brioche", Ingredient.UNIT_UNIT, "1.20", "60"),
            ("Hambúrguer bovino 160g", Ingredient.UNIT_UNIT, "5.90", "80"),
            ("Hambúrguer bovino 200g", Ingredient.UNIT_UNIT, "7.20", "60"),
            ("Patê vegano 150g", Ingredient.UNIT_UNIT, "6.50", "20"),
            ("Queijo cheddar", Ingredient.UNIT_UNIT, "1.10", "60"),
            ("Alface", Ingredient.UNIT_UNIT, "0.30", "40"),
            ("Tomate fatiado", Ingredient.UNIT_UNIT, "0.40", "40"),
            ("Batata palha premium", Ingredient.UNIT_KG, "9.00", "15"),
            ("Cebola em anéis", Ingredient.UNIT_KG, "4.50", "10"),
            ("Pó de chocolate", Ingredient.UNIT_KG, "18.00", "5"),
            ("Leite integral", Ingredient.UNIT_L, "4.20", "10"),
            ("Base brownie", Ingredient.UNIT_UNIT, "3.50", "30"),
            ("Sorvete baunilha", Ingredient.UNIT_UNIT, "2.80", "30"),
            ("Lata refrigerante 350ml", Ingredient.UNIT_UNIT, "3.20", "120"),
        ]
        return {name: self._upsert(Ingredient, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"unit": unit, "average_cost": Decimal(cost), "minimum_stock": Decimal(minimum), "is_active": True, "created_by": user, "updated_by": user}) for name, unit, cost, minimum in data}

    def _seed_products_burger(self, account, restaurant, branch, cats, user):
        data = [
            # code, name, cat, desc, price, cost, type, sector, stock
            ("BP-XSIMPLES", "X-Burger Simples", "Burgers", "Pão brioche, hambúrguer 160g, queijo, alface e tomate.", "26.90", "8.90", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-XDUPLO", "X-Burger Duplo", "Burgers", "Dois hambúrgueres 160g, queijo duplo e molho especial.", "39.90", "14.20", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-XBACON", "X-Bacon Crispy", "Burgers", "Hambúrguer 200g, bacon crispy, queijo e molho defumado.", "42.90", "15.80", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-XVEGANO", "X-Burger Vegano", "Burgers", "Patê vegano, queijo vegetal, alface, tomate e maionese vegana.", "34.90", "10.50", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-BATATA", "Batata Frita", "Acompanhamentos", "Porção crocante 250g.", "16.90", "5.40", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-ONION", "Onion Rings", "Acompanhamentos", "Anéis de cebola empanados 200g.", "19.90", "6.80", Product.TYPE_MEAL, Product.SECTOR_KITCHEN, True),
            ("BP-SHAKE", "Milkshake Chocolate", "Bebidas", "Copo 500ml com sorvete e calda.", "24.90", "8.50", Product.TYPE_DRINK, Product.SECTOR_BAR, False),
            ("BP-REFRI", "Refrigerante Lata", "Bebidas", "Lata 350ml gelada.", "7.00", "3.20", Product.TYPE_DRINK, Product.SECTOR_BAR, True),
            ("BP-AGUA", "Água Mineral", "Bebidas", "Garrafa 500ml.", "5.00", "1.50", Product.TYPE_DRINK, Product.SECTOR_BAR, False),
            ("BP-SUCO", "Suco Natural", "Bebidas", "Copo 400ml feito na hora.", "12.00", "4.20", Product.TYPE_DRINK, Product.SECTOR_BAR, False),
            ("BP-BROWNIE", "Brownie Fudge", "Sobremesas", "Fatia quentinha com sorvete.", "16.00", "5.80", Product.TYPE_DESSERT, Product.SECTOR_DESSERT, False),
            ("BP-SORVETE", "Sorvete 2 Bolas", "Sobremesas", "Escolha o sabor.", "10.00", "3.50", Product.TYPE_DESSERT, Product.SECTOR_DESSERT, False),
            ("BP-COMBO1", "Combo Clássico", "Combos", "X-Burger Simples + Batata + Refri.", "44.90", "17.50", Product.TYPE_COMBO, Product.SECTOR_KITCHEN, False),
            ("BP-COMBO2", "Combo Duplo", "Combos", "X-Burger Duplo + Batata + Shake.", "74.90", "28.40", Product.TYPE_COMBO, Product.SECTOR_KITCHEN, False),
        ]
        products = {}
        for code, name, cat_name, desc, price, cost, ptype, sector, cstock in data:
            margin = (Decimal(price) - Decimal(cost)) / Decimal(price) * 100
            products[code] = self._upsert(
                Product,
                {"account": account, "restaurant": restaurant, "branch": branch, "internal_code": code},
                {
                    "name": name, "description": desc,
                    "category": cats[cat_name],
                    "sale_price": Decimal(price),
                    "estimated_cost": Decimal(cost),
                    "margin_percent": margin.quantize(Decimal("0.01")),
                    "product_type": ptype,
                    "average_preparation_time": 12 if ptype == Product.TYPE_DRINK else 18,
                    "production_sector": sector,
                    "controls_stock": cstock,
                    "allows_addons": ptype in (Product.TYPE_MEAL, Product.TYPE_COMBO),
                    "allows_notes": True,
                    "available_for_table": True,
                    "available_for_counter": True,
                    "available_for_delivery": ptype != Product.TYPE_COMBO,
                    "is_active": True,
                    "created_by": user, "updated_by": user,
                },
            )

        # Produto pesavel: buffet self-service cobrado por kg (sale_price = preco do kilo).
        products["BP-KILO"] = self._upsert(
            Product,
            {"account": account, "restaurant": restaurant, "branch": branch, "internal_code": "BP-KILO"},
            {
                "name": "Refeição por Kilo",
                "description": "Buffet self-service pesado na balança. Preço por kg.",
                "category": cats["Self-service"],
                "sale_price": Decimal("69.90"),
                "estimated_cost": Decimal("28.00"),
                "margin_percent": Decimal("59.94"),
                "product_type": Product.TYPE_MEAL,
                "pricing_unit": Product.PRICING_KG,
                "average_preparation_time": 0,
                "production_sector": Product.SECTOR_KITCHEN,
                "controls_stock": False,
                "allows_addons": False,
                "allows_notes": True,
                "available_for_table": True,
                "available_for_counter": True,
                "available_for_delivery": False,
                "is_active": True,
                "created_by": user, "updated_by": user,
            },
        )
        return products

    def _seed_addons_burger(self, account, restaurant, branch, products, user):
        addons = [
            ("Bacon extra", "5.00", Product.SECTOR_KITCHEN, ["BP-XSIMPLES", "BP-XDUPLO", "BP-XBACON"]),
            ("Queijo extra", "4.00", Product.SECTOR_KITCHEN, ["BP-XSIMPLES", "BP-XDUPLO", "BP-XBACON", "BP-XVEGANO"]),
            ("Ovo frito", "3.50", Product.SECTOR_KITCHEN, ["BP-XSIMPLES", "BP-XDUPLO"]),
            ("Molho especial extra", "2.00", Product.SECTOR_KITCHEN, ["BP-XSIMPLES", "BP-XDUPLO", "BP-XBACON", "BP-XVEGANO"]),
            ("Batata pequena extra", "8.00", Product.SECTOR_KITCHEN, ["BP-COMBO1", "BP-COMBO2"]),
        ]
        for name, price, sector, product_codes in addons:
            addon = self._upsert(
                ProductAddon,
                {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
                {"price": Decimal(price), "production_sector": sector, "is_active": True, "created_by": user, "updated_by": user},
            )
            addon.products.set([products[code] for code in product_codes])

    def _seed_variations_burger(self, account, restaurant, branch, products, user):
        variations = [
            ("BP-XSIMPLES", [("Ao Ponto", "0.00"), ("Bem Passado", "0.00"), ("Mal Passado", "0.00")]),
            ("BP-XDUPLO", [("Ao Ponto", "0.00"), ("Bem Passado", "0.00")]),
            ("BP-XBACON", [("Ao Ponto", "0.00"), ("Bem Passado", "0.00")]),
            ("BP-SHAKE", [("Chocolate", "0.00"), ("Morango", "0.00"), ("Baunilha", "0.00")]),
            ("BP-SORVETE", [("Creme", "0.00"), ("Chocolate", "0.00"), ("Morango", "2.00")]),
        ]
        for code, vars_data in variations:
            for vname, delta in vars_data:
                self._upsert(
                    ProductVariation,
                    {"account": account, "restaurant": restaurant, "branch": branch, "product": products[code], "name": vname},
                    {"price_delta": Decimal(delta), "is_active": True, "created_by": user, "updated_by": user},
                )

    def _seed_recipes_burger(self, account, restaurant, branch, products, ingredients, user):
        recipes = {
            "BP-XSIMPLES": [
                ("Pão brioche", "1", Ingredient.UNIT_UNIT),
                ("Hambúrguer bovino 160g", "1", Ingredient.UNIT_UNIT),
                ("Queijo cheddar", "1", Ingredient.UNIT_UNIT),
                ("Alface", "1", Ingredient.UNIT_UNIT),
                ("Tomate fatiado", "1", Ingredient.UNIT_UNIT),
            ],
            "BP-XDUPLO": [
                ("Pão brioche", "1", Ingredient.UNIT_UNIT),
                ("Hambúrguer bovino 160g", "2", Ingredient.UNIT_UNIT),
                ("Queijo cheddar", "2", Ingredient.UNIT_UNIT),
                ("Alface", "1", Ingredient.UNIT_UNIT),
                ("Tomate fatiado", "1", Ingredient.UNIT_UNIT),
            ],
            "BP-XBACON": [
                ("Pão brioche", "1", Ingredient.UNIT_UNIT),
                ("Hambúrguer bovino 200g", "1", Ingredient.UNIT_UNIT),
                ("Queijo cheddar", "1", Ingredient.UNIT_UNIT),
            ],
            "BP-XVEGANO": [
                ("Pão brioche", "1", Ingredient.UNIT_UNIT),
                ("Patê vegano 150g", "1", Ingredient.UNIT_UNIT),
                ("Alface", "1", Ingredient.UNIT_UNIT),
                ("Tomate fatiado", "1", Ingredient.UNIT_UNIT),
            ],
            "BP-BATATA": [("Batata palha premium", "0.25", Ingredient.UNIT_KG)],
            "BP-ONION": [("Cebola em anéis", "0.20", Ingredient.UNIT_KG)],
            "BP-SHAKE": [
                ("Pó de chocolate", "0.05", Ingredient.UNIT_KG),
                ("Leite integral", "0.40", Ingredient.UNIT_L),
                ("Sorvete baunilha", "1", Ingredient.UNIT_UNIT),
            ],
            "BP-REFRI": [("Lata refrigerante 350ml", "1", Ingredient.UNIT_UNIT)],
            "BP-BROWNIE": [("Base brownie", "1", Ingredient.UNIT_UNIT), ("Sorvete baunilha", "1", Ingredient.UNIT_UNIT)],
        }
        self._build_recipes(account, restaurant, branch, products, ingredients, recipes, user)

    def _seed_menus_burger(self, account, restaurant, branch, products, user):
        menus_data = [
            ("Cardápio Principal", f"burger-palace-{branch.id}-principal", Menu.CHANNEL_ALL, None, None, list(products.keys())),
            ("Cardápio Delivery", f"burger-palace-{branch.id}-delivery", Menu.CHANNEL_DELIVERY, None, None, [k for k in products if k not in ("BP-COMBO1", "BP-COMBO2", "BP-KILO")]),
            ("Cardápio Digital QR", f"burger-palace-{branch.id}-digital", Menu.CHANNEL_DIGITAL, time(11, 0), time(23, 0), list(products.keys())),
        ]
        for name, slug, channel, avail_from, avail_until, codes in menus_data:
            menu = self._upsert(
                Menu,
                {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
                {"slug": slug, "channel": channel, "is_active": True, "available_from": avail_from, "available_until": avail_until, "created_by": user, "updated_by": user},
            )
            for order, code in enumerate(codes):
                self._upsert(
                    MenuItem,
                    {"account": account, "restaurant": restaurant, "branch": branch, "menu": menu, "product": products[code]},
                    {"display_order": order, "override_price": None, "is_active": True, "created_by": user, "updated_by": user},
                )

    def _seed_customers_burger(self, account, restaurant, branch, user):
        data = [
            ("Ana Souza", "(21) 90000-0001", "ana@starchef.test", "Rua das Flores", "45", "Copacabana"),
            ("Bruno Lima", "(21) 90000-0002", "bruno@starchef.test", "Av. Atlântica", "1000", "Copacabana"),
            ("Carla Mendes", "(21) 90000-0003", "carla@starchef.test", "Rua Augusta", "321", "Ipanema"),
            ("Diego Rocha", "(21) 90000-0004", "diego@starchef.test", "Rua Barata Ribeiro", "88", "Copacabana"),
            ("Elena Barbosa", "(21) 90000-0005", "elena@starchef.test", "Av. Nossa Sra. Copacabana", "500", "Copacabana"),
            ("Flávio Santos", "(21) 90000-0006", "flavio@starchef.test", "Rua Figueiredo Magalhães", "10", "Copacabana"),
            ("Gabriela Rios", "(21) 90000-0007", "gabriela@starchef.test", "Rua Domingos Ferreira", "220", "Copacabana"),
            ("Hugo Figueiredo", "(21) 90000-0008", "hugo@starchef.test", "Rua Raul Pompéia", "135", "Copacabana"),
        ]
        return self._build_customers(account, restaurant, branch, user, data)

    def _seed_orders_burger(self, branch, tables, products, customers, pms, admin, garcom, caixa):
        TYPE_TABLE = Order.TYPE_TABLE
        TYPE_DELIVERY = Order.TYPE_DELIVERY
        TYPE_COUNTER = Order.TYPE_COUNTER
        TYPE_TAKEAWAY = Order.TYPE_TAKEAWAY
        P = products
        C = customers

        # Pedido aberto: mesa 1 (não pago, cozinha)
        if not Order.all_objects.filter(branch=branch, general_notes="seed:burger:open:mesa1").exists():
            t = tables["1"]
            if t.status == Table.STATUS_FREE:
                o = create_order(restaurant=branch.restaurant, branch=branch, order_type=TYPE_TABLE, table=t, user=garcom, general_notes="seed:burger:open:mesa1")
                add_order_item(order=o, product=P["BP-XSIMPLES"], quantity=2, user=garcom, customer_note="Sem cebola")
                add_order_item(order=o, product=P["BP-BATATA"], quantity=2, user=garcom)
                add_order_item(order=o, product=P["BP-REFRI"], quantity=2, user=garcom)
                send_order_to_kitchen(o, garcom)

        # Pedido aberto: delivery em andamento
        if not Order.all_objects.filter(branch=branch, general_notes="seed:burger:open:delivery").exists():
            cust = C.get("Ana Souza")
            if cust:
                o = create_order(restaurant=branch.restaurant, branch=branch, order_type=TYPE_DELIVERY, customer=cust, delivery_address=cust.addresses.first(), delivery_fee=Decimal("8.00"), user=caixa, general_notes="seed:burger:open:delivery")
                add_order_item(order=o, product=P["BP-XDUPLO"], quantity=1, user=caixa)
                add_order_item(order=o, product=P["BP-ONION"], quantity=1, user=caixa)
                add_order_item(order=o, product=P["BP-SHAKE"], quantity=1, user=caixa)
                send_order_to_kitchen(o, caixa)

        # Histórico de pedidos pagos (7 dias × ~7 pedidos = 49 pedidos)
        today = timezone.localdate()
        history = [
            # (days_ago, type, table, customer_name, [(code, qty)], method, hour, min, user)
            # Dia 6
            (6, TYPE_TABLE, "2", None, [("BP-XSIMPLES", 2), ("BP-BATATA", 1), ("BP-REFRI", 2)], "Cartão Crédito", 12, 0, garcom),
            (6, TYPE_DELIVERY, None, "Ana Souza", [("BP-XDUPLO", 1), ("BP-ONION", 1), ("BP-SUCO", 1)], "PIX", 19, 30, caixa),
            (6, TYPE_COUNTER, None, None, [("BP-XSIMPLES", 1), ("BP-REFRI", 1)], "Dinheiro", 13, 45, caixa),
            (6, TYPE_TAKEAWAY, None, "Bruno Lima", [("BP-COMBO1", 2), ("BP-AGUA", 2)], "PIX", 20, 0, caixa),
            (6, TYPE_TABLE, "3", None, [("BP-XBACON", 2), ("BP-BATATA", 2), ("BP-SHAKE", 2)], "Cartão Crédito", 21, 15, garcom),
            (6, TYPE_COUNTER, None, None, [("BP-XVEGANO", 1), ("BP-SUCO", 1)], "Débito", 14, 20, caixa),
            (6, TYPE_TABLE, "5", None, [("BP-XDUPLO", 3), ("BP-ONION", 1), ("BP-REFRI", 3)], "Dinheiro", 20, 30, garcom),
            # Dia 5
            (5, TYPE_TABLE, "4", None, [("BP-XSIMPLES", 4), ("BP-BATATA", 2), ("BP-REFRI", 4)], "Voucher", 12, 30, garcom),
            (5, TYPE_DELIVERY, None, "Carla Mendes", [("BP-XVEGANO", 1), ("BP-SUCO", 1), ("BP-BROWNIE", 1)], "PIX", 18, 0, caixa),
            (5, TYPE_COUNTER, None, None, [("BP-XSIMPLES", 2), ("BP-ONION", 1), ("BP-AGUA", 2)], "Débito", 14, 0, caixa),
            (5, TYPE_TABLE, "6", None, [("BP-COMBO2", 2), ("BP-REFRI", 2)], "Cartão Crédito", 19, 45, garcom),
            (5, TYPE_TAKEAWAY, None, "Diego Rocha", [("BP-XBACON", 1), ("BP-BATATA", 1), ("BP-REFRI", 1)], "PIX", 17, 30, caixa),
            (5, TYPE_DELIVERY, None, "Elena Barbosa", [("BP-XDUPLO", 2), ("BP-SUCO", 2)], "PIX", 20, 15, caixa),
            (5, TYPE_TABLE, "7", None, [("BP-XSIMPLES", 2), ("BP-SORVETE", 2)], "Dinheiro", 22, 0, garcom),
            # Dia 4
            (4, TYPE_TABLE, "2", None, [("BP-XSIMPLES", 3), ("BP-BATATA", 2), ("BP-REFRI", 3)], "Cartão Crédito", 13, 0, garcom),
            (4, TYPE_DELIVERY, None, "Flávio Santos", [("BP-XBACON", 1), ("BP-ONION", 1), ("BP-SHAKE", 1)], "PIX", 19, 0, caixa),
            (4, TYPE_COUNTER, None, None, [("BP-XVEGANO", 2), ("BP-SUCO", 2)], "PIX", 15, 30, caixa),
            (4, TYPE_TABLE, "8", None, [("BP-COMBO1", 4), ("BP-REFRI", 4)], "Voucher", 20, 0, garcom),
            (4, TYPE_TAKEAWAY, None, "Gabriela Rios", [("BP-XSIMPLES", 2), ("BP-BROWNIE", 2)], "Débito", 18, 45, caixa),
            (4, TYPE_DELIVERY, None, "Hugo Figueiredo", [("BP-XDUPLO", 1), ("BP-BATATA", 1), ("BP-REFRI", 1)], "PIX", 21, 30, caixa),
            (4, TYPE_TABLE, "9", None, [("BP-XBACON", 2), ("BP-SHAKE", 2)], "Cartão Crédito", 12, 45, garcom),
            # Dia 3
            (3, TYPE_TABLE, "3", None, [("BP-XDUPLO", 2), ("BP-BATATA", 1), ("BP-REFRI", 2)], "Dinheiro", 12, 0, garcom),
            (3, TYPE_DELIVERY, None, "Ana Souza", [("BP-XVEGANO", 1), ("BP-SUCO", 1)], "PIX", 18, 30, caixa),
            (3, TYPE_COUNTER, None, None, [("BP-XSIMPLES", 3), ("BP-ONION", 1), ("BP-REFRI", 2)], "Débito", 13, 0, caixa),
            (3, TYPE_TABLE, "10", None, [("BP-COMBO2", 3), ("BP-REFRI", 3)], "Cartão Crédito", 21, 0, garcom),
            (3, TYPE_TAKEAWAY, None, "Bruno Lima", [("BP-XBACON", 2), ("BP-BATATA", 2), ("BP-AGUA", 2)], "PIX", 19, 15, caixa),
            (3, TYPE_TABLE, "4", None, [("BP-XSIMPLES", 2), ("BP-BROWNIE", 2), ("BP-SUCO", 2)], "Voucher", 14, 30, garcom),
            # Dia 2
            (2, TYPE_TABLE, "5", None, [("BP-XDUPLO", 4), ("BP-BATATA", 2), ("BP-REFRI", 4)], "Cartão Crédito", 12, 30, garcom),
            (2, TYPE_DELIVERY, None, "Carla Mendes", [("BP-XSIMPLES", 2), ("BP-ONION", 1), ("BP-SUCO", 2)], "PIX", 19, 45, caixa),
            (2, TYPE_COUNTER, None, None, [("BP-XVEGANO", 1), ("BP-REFRI", 1)], "Dinheiro", 11, 30, caixa),
            (2, TYPE_TABLE, "6", None, [("BP-COMBO1", 3), ("BP-SHAKE", 3)], "Débito", 20, 30, garcom),
            (2, TYPE_TAKEAWAY, None, "Diego Rocha", [("BP-XBACON", 1), ("BP-SORVETE", 2)], "PIX", 17, 0, caixa),
            (2, TYPE_DELIVERY, None, "Elena Barbosa", [("BP-XDUPLO", 1), ("BP-BATATA", 1), ("BP-REFRI", 1)], "PIX", 21, 0, caixa),
            # Dia 1
            (1, TYPE_TABLE, "7", None, [("BP-XSIMPLES", 3), ("BP-BATATA", 2), ("BP-REFRI", 3)], "Dinheiro", 13, 0, garcom),
            (1, TYPE_DELIVERY, None, "Flávio Santos", [("BP-XVEGANO", 1), ("BP-SUCO", 1), ("BP-BROWNIE", 1)], "PIX", 18, 15, caixa),
            (1, TYPE_COUNTER, None, None, [("BP-XSIMPLES", 1), ("BP-ONION", 1), ("BP-AGUA", 1)], "Débito", 14, 45, caixa),
            (1, TYPE_TABLE, "8", None, [("BP-COMBO2", 2), ("BP-REFRI", 2)], "Cartão Crédito", 21, 30, garcom),
            (1, TYPE_TAKEAWAY, None, "Gabriela Rios", [("BP-XBACON", 1), ("BP-BATATA", 1), ("BP-SHAKE", 1)], "PIX", 19, 30, caixa),
            # Hoje — vários horários para popular gráfico por hora
            (0, TYPE_TABLE, "2", None, [("BP-XSIMPLES", 2), ("BP-REFRI", 2)], "Dinheiro", 11, 30, garcom),
            (0, TYPE_COUNTER, None, None, [("BP-XVEGANO", 1), ("BP-SUCO", 1)], "Débito", 12, 15, caixa),
            (0, TYPE_TABLE, "3", None, [("BP-XDUPLO", 2), ("BP-BATATA", 2), ("BP-REFRI", 2)], "Cartão Crédito", 13, 0, garcom),
            (0, TYPE_DELIVERY, None, "Bruno Lima", [("BP-XBACON", 1), ("BP-ONION", 1)], "PIX", 14, 30, caixa),
            (0, TYPE_COUNTER, None, None, [("BP-COMBO1", 1), ("BP-REFRI", 1)], "Dinheiro", 15, 45, caixa),
            (0, TYPE_TABLE, "4", None, [("BP-XSIMPLES", 4), ("BP-BATATA", 2), ("BP-REFRI", 4)], "Voucher", 18, 0, garcom),
            (0, TYPE_DELIVERY, None, "Ana Souza", [("BP-XDUPLO", 1), ("BP-SUCO", 1), ("BP-BROWNIE", 1)], "PIX", 19, 0, caixa),
            (0, TYPE_TABLE, "5", None, [("BP-COMBO2", 2), ("BP-SHAKE", 2)], "Cartão Crédito", 20, 0, garcom),
        ]

        method_map = {"Cartão Crédito": "Cartão de Crédito", "Débito": "Cartão de Débito", "Dinheiro": "Dinheiro", "PIX": "PIX", "Voucher": "Voucher Refeição"}
        for idx, (days_ago, otype, table_num, cust_name, items, method_label, hour, minute, responsible) in enumerate(history, start=1):
            note = f"seed:burger:hist:{idx}"
            if Order.all_objects.filter(branch=branch, general_notes=note).exists():
                continue
            cust = customers.get(cust_name) if cust_name else None
            kwargs = {"general_notes": note}
            if otype == TYPE_TABLE:
                kwargs["table"] = tables[table_num]
            if cust:
                kwargs["customer"] = cust
            if otype == TYPE_DELIVERY and cust:
                kwargs["delivery_address"] = cust.addresses.first()
                kwargs["delivery_fee"] = Decimal("8.00")
            order = create_order(restaurant=branch.restaurant, branch=branch, order_type=otype, user=responsible, **kwargs)
            for code, qty in items:
                add_order_item(order=order, product=products[code], quantity=qty, user=responsible)
            order = close_order(order, responsible)
            pm_name = method_map.get(method_label, method_label)
            pm = pms.get(pm_name)
            if pm is None:
                pm = next(iter(pms.values()))
            payment = register_payment(order=order, user=caixa, payment_method_id=pm.id, amount=order.total, idempotency_key=f"seed-burger-{idx}", metadata={"source": "seed_demo"})
            opened_at = self._dt(today - timedelta(days=days_ago), hour, minute)
            closed_at = opened_at + timedelta(minutes=25 + (idx % 20))
            self._backfill_order(order, payment, opened_at, closed_at)

    # ═══════════════════════════════════════════════════════════════════════════
    # TENANT 1 — Restaurante 2: Pizza Rustica (Botafogo)
    # ═══════════════════════════════════════════════════════════════════════════

    def _seed_pizza_rustica(self, account, restaurant, branch, gerente, *, skip_orders):
        u = gerente
        _, tables = self._seed_tables_pizza(account, restaurant, branch, u)
        pms = self._seed_payment_methods(account, restaurant, branch, u)
        stock_loc = self._seed_stock_location(account, restaurant, branch, u, "Estoque Pizza Rustica")
        self._seed_printers_pizza(account, restaurant, branch, u)
        self._seed_delivery_zones_pizza(account, restaurant, branch, u)
        self._seed_deliveryman_pizza(account, restaurant, branch, u)
        cats = self._seed_categories_pizza(account, restaurant, branch, u)
        ingrs = self._seed_ingredients_pizza(account, restaurant, branch, u)
        prods = self._seed_products_pizza(account, restaurant, branch, cats, u)
        self._seed_recipes_pizza(account, restaurant, branch, prods, ingrs, u)
        self._seed_menus_pizza(account, restaurant, branch, prods, u)
        customers = self._seed_customers_pizza(account, restaurant, branch, u)
        self._seed_stock_movements(account, restaurant, branch, ingrs, stock_loc, u)
        if not skip_orders:
            cash_register = self._seed_cash_register(branch, u)
            self._seed_orders_pizza(branch, tables, prods, customers, pms, u)
            self._seed_current_cash_movements(cash_register, u)

    def _seed_tables_pizza(self, account, restaurant, branch, user):
        sectors = {
            "salao": self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Salão"}, {"display_order": 1, "is_active": True, "created_by": user, "updated_by": user}),
            "terraco": self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Terraço"}, {"display_order": 2, "is_active": True, "created_by": user, "updated_by": user}),
        }
        tables = {}
        for n in range(1, 9):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sectors["salao"], "capacity": 4, "is_active": True, "created_by": user, "updated_by": user})
        for n in range(9, 11):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sectors["terraco"], "capacity": 6, "is_active": True, "created_by": user, "updated_by": user})
        return sectors, tables

    def _seed_printers_pizza(self, account, restaurant, branch, user):
        # sector agora é FK opcional a TableSector — o demo deixa sem setor.
        for name, sector, auto in [("Cozinha", None, True), ("Bar", None, True), ("Caixa", None, False)]:
            self._upsert(Printer, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"sector": sector, "driver_type": Printer.DRIVER_BROWSER, "endpoint": "", "auto_print": auto, "is_active": True, "settings": {"demo": True}, "created_by": user, "updated_by": user})

    def _seed_delivery_zones_pizza(self, account, restaurant, branch, user):
        zones = [
            ("Botafogo / Flamengo (grátis)", "0", "2.5", "0.00", 25),
            ("Catete / Glória (3-5km)", "2.5", "5", "7.00", 40),
        ]
        for name, r_min, r_max, fee, minutes in zones:
            self._upsert(DeliveryZone, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"min_radius_km": Decimal(r_min), "max_radius_km": Decimal(r_max), "delivery_fee": Decimal(fee), "estimated_minutes": minutes, "is_active": True, "created_by": user, "updated_by": user})

    def _seed_deliveryman_pizza(self, account, restaurant, branch, user):
        self._upsert(Deliveryman, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Ricardo Alves"}, {"phone": "(21) 98002-0001", "vehicle_type": Deliveryman.VEHICLE_MOTORCYCLE, "vehicle_plate": "RIO-0010", "is_active": True, "created_by": user, "updated_by": user})

    def _seed_categories_pizza(self, account, restaurant, branch, user):
        cats = [("Entradas", 1), ("Pizzas", 2), ("Massas", 3), ("Bebidas", 4), ("Sobremesas", 5)]
        return {name: self._upsert(ProductCategory, {"account": account, "restaurant": restaurant, "branch": branch, "name": name, "parent": None}, {"display_order": order, "is_active": True, "created_by": user, "updated_by": user}) for name, order in cats}

    def _seed_ingredients_pizza(self, account, restaurant, branch, user):
        data = [
            ("Massa pizza", Ingredient.UNIT_UNIT, "3.50", "40"),
            ("Molho de tomate", Ingredient.UNIT_L, "5.00", "8"),
            ("Mozzarella fior di latte", Ingredient.UNIT_KG, "32.00", "5"),
            ("Pepperoni fatiado", Ingredient.UNIT_KG, "45.00", "3"),
            ("Gorgonzola", Ingredient.UNIT_KG, "55.00", "2"),
            ("Parmigiano Reggiano", Ingredient.UNIT_KG, "60.00", "2"),
            ("Espaguete", Ingredient.UNIT_KG, "8.50", "5"),
            ("Carne bovina moída", Ingredient.UNIT_KG, "22.00", "5"),
        ]
        return {name: self._upsert(Ingredient, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"unit": unit, "average_cost": Decimal(cost), "minimum_stock": Decimal(minimum), "is_active": True, "created_by": user, "updated_by": user}) for name, unit, cost, minimum in data}

    def _seed_products_pizza(self, account, restaurant, branch, cats, user):
        data = [
            ("PR-BRUS", "Bruschetta", "Entradas", "Pão italiano, tomate e manjericão.", "24.00", "7.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-MARG", "Pizza Margherita", "Pizzas", "Molho de tomate, mozzarella e manjericão fresco.", "58.00", "18.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-PEPP", "Pizza Pepperoni", "Pizzas", "Molho, mozzarella e pepperoni premium.", "68.00", "22.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-4Q", "Pizza Quattro Formaggi", "Pizzas", "Quatro queijos artesanais.", "74.00", "26.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-ESPA", "Espaguete Bolonhesa", "Massas", "Molho bolonhesa caseiro com ervas.", "42.00", "13.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-PAPP", "Pappardelle Cogumelos", "Massas", "Massa larga com ragu de cogumelos.", "48.00", "16.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("PR-VINHO", "Vinho Tinto (Taça)", "Bebidas", "Seleção da casa.", "28.00", "10.00", Product.TYPE_DRINK, Product.SECTOR_BAR),
            ("PR-AGUA", "Água Mineral", "Bebidas", "500ml.", "6.00", "1.50", Product.TYPE_DRINK, Product.SECTOR_BAR),
            ("PR-REFRI", "Refrigerante", "Bebidas", "Lata 350ml.", "7.00", "3.20", Product.TYPE_DRINK, Product.SECTOR_BAR),
            ("PR-TIRAM", "Tiramisù", "Sobremesas", "Receita tradicional italiana.", "22.00", "8.00", Product.TYPE_DESSERT, Product.SECTOR_DESSERT),
        ]
        products = {}
        for code, name, cat_name, desc, price, cost, ptype, sector in data:
            margin = (Decimal(price) - Decimal(cost)) / Decimal(price) * 100
            products[code] = self._upsert(
                Product,
                {"account": account, "restaurant": restaurant, "branch": branch, "internal_code": code},
                {"name": name, "description": desc, "category": cats[cat_name], "sale_price": Decimal(price), "estimated_cost": Decimal(cost), "margin_percent": margin.quantize(Decimal("0.01")), "product_type": ptype, "average_preparation_time": 20, "production_sector": sector, "controls_stock": False, "allows_addons": True, "allows_notes": True, "available_for_table": True, "available_for_counter": True, "available_for_delivery": True, "is_active": True, "created_by": user, "updated_by": user},
            )
        return products

    def _seed_recipes_pizza(self, account, restaurant, branch, products, ingredients, user):
        recipes = {
            "PR-MARG": [("Massa pizza", "1", Ingredient.UNIT_UNIT), ("Molho de tomate", "0.15", Ingredient.UNIT_L), ("Mozzarella fior di latte", "0.20", Ingredient.UNIT_KG)],
            "PR-PEPP": [("Massa pizza", "1", Ingredient.UNIT_UNIT), ("Molho de tomate", "0.15", Ingredient.UNIT_L), ("Mozzarella fior di latte", "0.15", Ingredient.UNIT_KG), ("Pepperoni fatiado", "0.12", Ingredient.UNIT_KG)],
            "PR-4Q": [("Massa pizza", "1", Ingredient.UNIT_UNIT), ("Molho de tomate", "0.10", Ingredient.UNIT_L), ("Mozzarella fior di latte", "0.12", Ingredient.UNIT_KG), ("Gorgonzola", "0.08", Ingredient.UNIT_KG), ("Parmigiano Reggiano", "0.06", Ingredient.UNIT_KG)],
            "PR-ESPA": [("Espaguete", "0.20", Ingredient.UNIT_KG), ("Carne bovina moída", "0.18", Ingredient.UNIT_KG), ("Molho de tomate", "0.15", Ingredient.UNIT_L)],
        }
        self._build_recipes(account, restaurant, branch, products, ingredients, recipes, user)

    def _seed_menus_pizza(self, account, restaurant, branch, products, user):
        menus_data = [
            ("Cardápio Pizza Rustica", f"pizza-rustica-{branch.id}-principal", Menu.CHANNEL_ALL, list(products.keys())),
            ("Cardápio Delivery Pizza", f"pizza-rustica-{branch.id}-delivery", Menu.CHANNEL_DELIVERY, [k for k in products if k not in ("PR-BRUS",)]),
        ]
        for name, slug, channel, codes in menus_data:
            menu = self._upsert(Menu, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"slug": slug, "channel": channel, "is_active": True, "available_from": None, "available_until": None, "created_by": user, "updated_by": user})
            for order, code in enumerate(codes):
                self._upsert(MenuItem, {"account": account, "restaurant": restaurant, "branch": branch, "menu": menu, "product": products[code]}, {"display_order": order, "override_price": None, "is_active": True, "created_by": user, "updated_by": user})

    def _seed_customers_pizza(self, account, restaurant, branch, user):
        data = [
            ("Beatriz Cardoso", "(21) 90003-0001", "beatriz@starchef.test", "Rua São João Batista", "50", "Botafogo"),
            ("Rafael Nunes", "(21) 90003-0002", "rafael@starchef.test", "Rua Bambina", "120", "Botafogo"),
            ("Juliana Castro", "(21) 90003-0003", "juliana@starchef.test", "Rua Passagem", "80", "Botafogo"),
            ("Leonardo Pires", "(21) 90003-0004", "leonardo@starchef.test", "Av. Lauro Sodré", "30", "Catete"),
        ]
        return self._build_customers(account, restaurant, branch, user, data)

    def _seed_orders_pizza(self, branch, tables, products, customers, pms, gerente):
        TYPE_TABLE = Order.TYPE_TABLE
        TYPE_DELIVERY = Order.TYPE_DELIVERY
        TYPE_COUNTER = Order.TYPE_COUNTER
        P = products
        C = customers
        today = timezone.localdate()

        # Pedido aberto: mesa 9 (VIP)
        if not Order.all_objects.filter(branch=branch, general_notes="seed:pizza:open:mesa9").exists():
            t = tables["9"]
            if t.status == Table.STATUS_FREE:
                o = create_order(restaurant=branch.restaurant, branch=branch, order_type=TYPE_TABLE, table=t, user=gerente, general_notes="seed:pizza:open:mesa9")
                add_order_item(order=o, product=P["PR-MARG"], quantity=1, user=gerente)
                add_order_item(order=o, product=P["PR-PEPP"], quantity=1, user=gerente)
                add_order_item(order=o, product=P["PR-VINHO"], quantity=2, user=gerente)
                send_order_to_kitchen(o, gerente)

        history = [
            # (days_ago, type, table, customer, items, method, hour, min)
            (6, TYPE_TABLE, "1", None, [("PR-MARG", 1), ("PR-VINHO", 2)], "PIX", 19, 0),
            (6, TYPE_DELIVERY, None, "Beatriz Cardoso", [("PR-PEPP", 1), ("PR-REFRI", 2)], "PIX", 20, 30),
            (6, TYPE_TABLE, "2", None, [("PR-4Q", 1), ("PR-ESPA", 1), ("PR-AGUA", 2)], "Cartão Crédito", 21, 0),
            (6, TYPE_TABLE, "3", None, [("PR-BRUS", 2), ("PR-PAPP", 2), ("PR-VINHO", 2)], "Cartão Crédito", 19, 30),
            (5, TYPE_TABLE, "4", None, [("PR-MARG", 2), ("PR-REFRI", 4)], "Dinheiro", 20, 0),
            (5, TYPE_DELIVERY, None, "Rafael Nunes", [("PR-4Q", 1), ("PR-TIRAM", 2)], "PIX", 21, 15),
            (5, TYPE_TABLE, "5", None, [("PR-ESPA", 2), ("PR-VINHO", 2)], "Débito", 19, 45),
            (5, TYPE_TABLE, "6", None, [("PR-PEPP", 1), ("PR-BRUS", 1), ("PR-AGUA", 2)], "PIX", 20, 30),
            (4, TYPE_TABLE, "1", None, [("PR-MARG", 1), ("PR-PAPP", 1), ("PR-VINHO", 1)], "Cartão Crédito", 19, 0),
            (4, TYPE_DELIVERY, None, "Juliana Castro", [("PR-ESPA", 1), ("PR-REFRI", 1)], "PIX", 20, 0),
            (4, TYPE_TABLE, "2", None, [("PR-4Q", 2), ("PR-TIRAM", 2)], "Dinheiro", 21, 30),
            (3, TYPE_TABLE, "3", None, [("PR-PEPP", 2), ("PR-VINHO", 4)], "PIX", 19, 30),
            (3, TYPE_DELIVERY, None, "Leonardo Pires", [("PR-MARG", 1), ("PR-BRUS", 1), ("PR-AGUA", 1)], "Débito", 20, 15),
            (3, TYPE_TABLE, "7", None, [("PR-ESPA", 2), ("PR-PAPP", 1), ("PR-VINHO", 2)], "Cartão Crédito", 21, 0),
            (2, TYPE_TABLE, "4", None, [("PR-4Q", 1), ("PR-BRUS", 1), ("PR-REFRI", 2)], "PIX", 19, 0),
            (2, TYPE_DELIVERY, None, "Beatriz Cardoso", [("PR-PEPP", 1), ("PR-TIRAM", 1)], "PIX", 20, 30),
            (2, TYPE_TABLE, "8", None, [("PR-MARG", 2), ("PR-VINHO", 2)], "Cartão Crédito", 21, 45),
            (1, TYPE_TABLE, "5", None, [("PR-ESPA", 3), ("PR-VINHO", 3)], "Dinheiro", 19, 30),
            (1, TYPE_DELIVERY, None, "Rafael Nunes", [("PR-4Q", 1), ("PR-REFRI", 2)], "PIX", 20, 0),
            (1, TYPE_TABLE, "6", None, [("PR-PEPP", 1), ("PR-PAPP", 1), ("PR-TIRAM", 2)], "Débito", 21, 30),
            (0, TYPE_TABLE, "2", None, [("PR-MARG", 2), ("PR-VINHO", 2)], "PIX", 19, 0),
            (0, TYPE_TABLE, "3", None, [("PR-4Q", 1), ("PR-BRUS", 2), ("PR-AGUA", 2)], "Cartão Crédito", 20, 30),
            (0, TYPE_DELIVERY, None, "Juliana Castro", [("PR-ESPA", 1), ("PR-TIRAM", 1)], "PIX", 21, 0),
        ]
        method_map = {"Cartão Crédito": "Cartão de Crédito", "Débito": "Cartão de Débito", "Dinheiro": "Dinheiro", "PIX": "PIX"}
        pm_list = list(pms.values())
        for idx, (days_ago, otype, table_num, cust_name, items, method_label, hour, minute) in enumerate(history, start=1):
            note = f"seed:pizza:hist:{idx}"
            if Order.all_objects.filter(branch=branch, general_notes=note).exists():
                continue
            cust = C.get(cust_name) if cust_name else None
            kwargs = {"general_notes": note}
            if otype == TYPE_TABLE:
                kwargs["table"] = tables[table_num]
            if cust:
                kwargs["customer"] = cust
            if otype == TYPE_DELIVERY and cust:
                kwargs["delivery_address"] = cust.addresses.first()
                kwargs["delivery_fee"] = Decimal("7.00")
            order = create_order(restaurant=branch.restaurant, branch=branch, order_type=otype, user=gerente, **kwargs)
            for code, qty in items:
                add_order_item(order=order, product=products[code], quantity=qty, user=gerente)
            order = close_order(order, gerente)
            pm_name = method_map.get(method_label, method_label)
            pm = pms.get(pm_name, pm_list[0])
            payment = register_payment(order=order, user=gerente, payment_method_id=pm.id, amount=order.total, idempotency_key=f"seed-pizza-{idx}", metadata={"source": "seed_demo"})
            opened_at = self._dt(today - timedelta(days=days_ago), hour, minute)
            closed_at = opened_at + timedelta(minutes=30 + (idx % 25))
            self._backfill_order(order, payment, opened_at, closed_at)

    # ═══════════════════════════════════════════════════════════════════════════
    # TENANT 2 — Bella Trattoria (Ipanema) — tenant isolado, 1 usuário
    # ═══════════════════════════════════════════════════════════════════════════

    def _seed_bella_trattoria(self, account, restaurant, branch, owner, *, skip_orders):
        u = owner
        _, tables = self._seed_tables_trattoria(account, restaurant, branch, u)
        pms = self._seed_payment_methods(account, restaurant, branch, u)
        stock_loc = self._seed_stock_location(account, restaurant, branch, u, "Estoque Bella Trattoria")
        cats = self._seed_categories_trattoria(account, restaurant, branch, u)
        ingrs = self._seed_ingredients_trattoria(account, restaurant, branch, u)
        prods = self._seed_products_trattoria(account, restaurant, branch, cats, u)
        self._seed_menus_trattoria(account, restaurant, branch, prods, u)
        customers = self._seed_customers_trattoria(account, restaurant, branch, u)
        self._seed_stock_movements(account, restaurant, branch, ingrs, stock_loc, u)
        if not skip_orders:
            cash_register = self._seed_cash_register(branch, u)
            self._seed_orders_trattoria(branch, tables, prods, customers, pms, u)
            self._seed_current_cash_movements(cash_register, u)

    def _seed_tables_trattoria(self, account, restaurant, branch, user):
        sector = self._upsert(TableSector, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Salão"}, {"display_order": 1, "is_active": True, "created_by": user, "updated_by": user})
        tables = {}
        for n in range(1, 9):
            tables[str(n)] = self._upsert(Table, {"account": account, "restaurant": restaurant, "branch": branch, "number": str(n)}, {"sector": sector, "capacity": 4, "is_active": True, "created_by": user, "updated_by": user})
        return {"salao": sector}, tables

    def _seed_categories_trattoria(self, account, restaurant, branch, user):
        cats = [("Entradas", 1), ("Massas", 2), ("Carnes", 3), ("Bebidas", 4), ("Sobremesas", 5)]
        return {name: self._upsert(ProductCategory, {"account": account, "restaurant": restaurant, "branch": branch, "name": name, "parent": None}, {"display_order": order, "is_active": True, "created_by": user, "updated_by": user}) for name, order in cats}

    def _seed_ingredients_trattoria(self, account, restaurant, branch, user):
        data = [
            ("Carpaccio bovino", Ingredient.UNIT_KG, "65.00", "2"),
            ("Arroz arbóreo", Ingredient.UNIT_KG, "18.00", "3"),
            ("Funghi secchi", Ingredient.UNIT_KG, "80.00", "1"),
            ("Ossobuco bovino", Ingredient.UNIT_KG, "40.00", "3"),
            ("Filé mignon", Ingredient.UNIT_KG, "90.00", "4"),
            ("Mascarpone", Ingredient.UNIT_KG, "42.00", "2"),
            ("Panna cotta base", Ingredient.UNIT_UNIT, "4.50", "20"),
        ]
        return {name: self._upsert(Ingredient, {"account": account, "restaurant": restaurant, "branch": branch, "name": name}, {"unit": unit, "average_cost": Decimal(cost), "minimum_stock": Decimal(minimum), "is_active": True, "created_by": user, "updated_by": user}) for name, unit, cost, minimum in data}

    def _seed_products_trattoria(self, account, restaurant, branch, cats, user):
        data = [
            ("BT-CARP", "Carpaccio di Manzo", "Entradas", "Carpaccio bovino com rúcula, parmesão e azeite trufado.", "42.00", "14.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("BT-RISO", "Risotto ai Funghi", "Massas", "Arroz arbóreo, funghi secchi e redução de vinho branco.", "58.00", "20.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("BT-TAGL", "Tagliatelle al Tartufo", "Massas", "Massa fresca com creme de trufas e parmesão.", "64.00", "22.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("BT-OSSO", "Ossobuco alla Milanese", "Carnes", "Ossobuco braseado com gremolata e risotto safran.", "78.00", "28.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("BT-FILE", "Filé ao Vinho Chianti", "Carnes", "Medalhão ao molho de vinho Chianti e legumes grelhados.", "88.00", "32.00", Product.TYPE_MEAL, Product.SECTOR_KITCHEN),
            ("BT-VINHO", "Vinho Chianti (Garrafa)", "Bebidas", "Chianti Classico selecionado.", "95.00", "38.00", Product.TYPE_DRINK, Product.SECTOR_BAR),
            ("BT-AGUA", "Água San Pellegrino", "Bebidas", "Garrafa 750ml.", "14.00", "5.00", Product.TYPE_DRINK, Product.SECTOR_BAR),
            ("BT-PANNA", "Panna Cotta", "Sobremesas", "Com calda de frutas vermelhas.", "26.00", "8.00", Product.TYPE_DESSERT, Product.SECTOR_DESSERT),
            ("BT-TIRAM", "Tiramisù della Casa", "Sobremesas", "Receita original com mascarpone e café.", "29.00", "10.00", Product.TYPE_DESSERT, Product.SECTOR_DESSERT),
        ]
        products = {}
        for code, name, cat_name, desc, price, cost, ptype, sector in data:
            margin = (Decimal(price) - Decimal(cost)) / Decimal(price) * 100
            products[code] = self._upsert(
                Product,
                {"account": account, "restaurant": restaurant, "branch": branch, "internal_code": code},
                {"name": name, "description": desc, "category": cats[cat_name], "sale_price": Decimal(price), "estimated_cost": Decimal(cost), "margin_percent": margin.quantize(Decimal("0.01")), "product_type": ptype, "average_preparation_time": 25, "production_sector": sector, "controls_stock": False, "allows_addons": False, "allows_notes": True, "available_for_table": True, "available_for_counter": False, "available_for_delivery": False, "is_active": True, "created_by": user, "updated_by": user},
            )
        return products

    def _seed_menus_trattoria(self, account, restaurant, branch, products, user):
        menu = self._upsert(Menu, {"account": account, "restaurant": restaurant, "branch": branch, "name": "Cardápio Bella Trattoria"}, {"slug": f"bella-trattoria-{branch.id}-principal", "channel": Menu.CHANNEL_ALL, "is_active": True, "available_from": None, "available_until": None, "created_by": user, "updated_by": user})
        for order, code in enumerate(products):
            self._upsert(MenuItem, {"account": account, "restaurant": restaurant, "branch": branch, "menu": menu, "product": products[code]}, {"display_order": order, "override_price": None, "is_active": True, "created_by": user, "updated_by": user})

    def _seed_customers_trattoria(self, account, restaurant, branch, user):
        data = [
            ("Isabella Romano", "(21) 90004-0001", "isabella@trattoria.test", "Rua Farme de Amoedo", "40", "Ipanema"),
            ("Matteo Ferrari", "(21) 90004-0002", "matteo@trattoria.test", "Rua Visconde de Pirajá", "150", "Ipanema"),
            ("Valentina Cruz", "(21) 90004-0003", "valentina@trattoria.test", "Av. Vieira Souto", "10", "Ipanema"),
        ]
        return self._build_customers(account, restaurant, branch, user, data)

    def _seed_orders_trattoria(self, branch, tables, products, customers, pms, owner):
        TYPE_TABLE = Order.TYPE_TABLE
        P = products
        C = customers
        today = timezone.localdate()

        # Pedido aberto
        if not Order.all_objects.filter(branch=branch, general_notes="seed:trattoria:open:mesa1").exists():
            t = tables["1"]
            if t.status == Table.STATUS_FREE:
                o = create_order(restaurant=branch.restaurant, branch=branch, order_type=TYPE_TABLE, table=t, user=owner, general_notes="seed:trattoria:open:mesa1")
                add_order_item(order=o, product=P["BT-CARP"], quantity=2, user=owner)
                add_order_item(order=o, product=P["BT-RISO"], quantity=2, user=owner)
                add_order_item(order=o, product=P["BT-VINHO"], quantity=1, user=owner)
                send_order_to_kitchen(o, owner)

        history = [
            (4, TYPE_TABLE, "2", "Isabella Romano", [("BT-RISO", 1), ("BT-OSSO", 1), ("BT-VINHO", 1)], "PIX", 20, 0),
            (4, TYPE_TABLE, "3", "Matteo Ferrari", [("BT-FILE", 1), ("BT-TIRAM", 1), ("BT-AGUA", 1)], "Cartão Crédito", 21, 30),
            (4, TYPE_TABLE, "4", None, [("BT-CARP", 2), ("BT-TAGL", 2), ("BT-VINHO", 1)], "Dinheiro", 19, 45),
            (3, TYPE_TABLE, "5", "Valentina Cruz", [("BT-OSSO", 2), ("BT-PANNA", 2), ("BT-VINHO", 1)], "PIX", 20, 30),
            (3, TYPE_TABLE, "2", None, [("BT-RISO", 2), ("BT-FILE", 1), ("BT-AGUA", 2)], "Cartão Crédito", 21, 0),
            (3, TYPE_TABLE, "6", "Isabella Romano", [("BT-CARP", 1), ("BT-TAGL", 1), ("BT-TIRAM", 1)], "Débito", 20, 0),
            (2, TYPE_TABLE, "3", "Matteo Ferrari", [("BT-FILE", 2), ("BT-VINHO", 2), ("BT-PANNA", 2)], "PIX", 19, 30),
            (2, TYPE_TABLE, "7", None, [("BT-OSSO", 1), ("BT-RISO", 1), ("BT-AGUA", 2)], "Cartão Crédito", 21, 0),
            (2, TYPE_TABLE, "4", "Valentina Cruz", [("BT-TAGL", 2), ("BT-TIRAM", 2)], "Dinheiro", 20, 30),
            (1, TYPE_TABLE, "5", "Isabella Romano", [("BT-CARP", 1), ("BT-FILE", 1), ("BT-VINHO", 1)], "PIX", 20, 0),
            (1, TYPE_TABLE, "6", None, [("BT-RISO", 2), ("BT-PANNA", 2), ("BT-AGUA", 2)], "Débito", 21, 30),
            (0, TYPE_TABLE, "2", "Matteo Ferrari", [("BT-OSSO", 1), ("BT-TIRAM", 1), ("BT-VINHO", 1)], "PIX", 19, 30),
            (0, TYPE_TABLE, "3", None, [("BT-FILE", 2), ("BT-CARP", 2), ("BT-AGUA", 2)], "Cartão Crédito", 21, 0),
        ]
        method_map = {"Cartão Crédito": "Cartão de Crédito", "Débito": "Cartão de Débito", "Dinheiro": "Dinheiro", "PIX": "PIX"}
        pm_list = list(pms.values())
        for idx, (days_ago, otype, table_num, cust_name, items, method_label, hour, minute) in enumerate(history, start=1):
            note = f"seed:trattoria:hist:{idx}"
            if Order.all_objects.filter(branch=branch, general_notes=note).exists():
                continue
            cust = C.get(cust_name) if cust_name else None
            kwargs = {"general_notes": note}
            if otype == TYPE_TABLE:
                kwargs["table"] = tables[table_num]
            if cust:
                kwargs["customer"] = cust
            order = create_order(restaurant=branch.restaurant, branch=branch, order_type=otype, user=owner, **kwargs)
            for code, qty in items:
                add_order_item(order=order, product=products[code], quantity=qty, user=owner)
            order = close_order(order, owner)
            pm_name = method_map.get(method_label, method_label)
            pm = pms.get(pm_name, pm_list[0])
            payment = register_payment(order=order, user=owner, payment_method_id=pm.id, amount=order.total, idempotency_key=f"seed-trattoria-{idx}", metadata={"source": "seed_demo"})
            opened_at = self._dt(today - timedelta(days=days_ago), hour, minute)
            closed_at = opened_at + timedelta(minutes=40 + (idx % 30))
            self._backfill_order(order, payment, opened_at, closed_at)

    # ═══════════════════════════════════════════════════════════════════════════
    # Helpers compartilhados
    # ═══════════════════════════════════════════════════════════════════════════

    def _seed_payment_methods(self, account, restaurant, branch, user):
        methods = {}
        data = [
            ("Dinheiro", PaymentMethod.TYPE_CASH, False),
            ("Cartão de Crédito", PaymentMethod.TYPE_CARD, True),
            ("Cartão de Débito", PaymentMethod.TYPE_CARD, True),
            ("PIX", PaymentMethod.TYPE_PIX, True),
            ("Voucher Refeição", PaymentMethod.TYPE_VOUCHER, True),
        ]
        for name, method_type, req_ref in data:
            methods[name] = self._upsert(
                PaymentMethod,
                {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
                {"method_type": method_type, "requires_reference": req_ref, "is_active": True, "created_by": user, "updated_by": user},
            )
        return methods

    def _seed_stock_location(self, account, restaurant, branch, user, name):
        return self._upsert(
            StockLocation,
            {"account": account, "restaurant": restaurant, "branch": branch, "name": name},
            {"description": "Estoque principal — seed demo.", "is_active": True, "created_by": user, "updated_by": user},
        )

    def _seed_stock_movements(self, account, restaurant, branch, ingredients, stock_location, user):
        for ingredient in ingredients.values():
            if StockMovement.all_objects.filter(account=account, branch=branch, ingredient=ingredient, location=stock_location, reason="Seed demo initial stock").exists():
                continue
            qty = max(ingredient.minimum_stock * Decimal("3"), Decimal("10"))
            StockMovement.all_objects.create(
                account=account, restaurant=restaurant, branch=branch,
                ingredient=ingredient, location=stock_location, operator=user,
                movement_type=StockMovement.TYPE_IN,
                quantity=qty, unit_cost=ingredient.average_cost,
                total_cost=(qty * ingredient.average_cost).quantize(Decimal("0.01")),
                reason="Seed demo initial stock",
                created_by=user, updated_by=user,
            )

    def _seed_cash_register(self, branch, user, extra_operators=None):
        restaurant = branch.restaurant
        station, _ = CashStation.all_objects.update_or_create(
            account=restaurant.account,
            restaurant=restaurant,
            code="CX-01",
            defaults={
                "name": "Caixa Principal",
                "cash_limit": Decimal("2500.00"),
                "is_active": True,
                "deleted_at": None,
                "settings": {"seed_demo": True},
                "created_by": user,
                "updated_by": user,
            },
        )
        # Um usuário só pode estar vinculado a um caixa por vez: o operador fica
        # no caixa principal e os operadores extras vão para o caixa de delivery.
        station.operators.set([user])

        secondary = None
        if extra_operators:
            secondary, _ = CashStation.all_objects.update_or_create(
                account=restaurant.account,
                restaurant=restaurant,
                code="CX-02",
                defaults={
                    "name": "Caixa Delivery",
                    "cash_limit": Decimal("1200.00"),
                    "is_active": True,
                    "deleted_at": None,
                    "settings": {"seed_demo": True},
                    "created_by": user,
                    "updated_by": user,
                },
            )
            secondary.operators.set(list(extra_operators))

        self._seed_closed_cash_session(branch, station, user)

        active_statuses = [
            CashRegister.STATUS_OPEN,
            CashRegister.STATUS_PENDING_OPENING,
            CashRegister.STATUS_PENDING_APPROVAL,
            CashRegister.STATUS_PENDING_CLOSING,
            CashRegister.STATUS_BLOCKED,
        ]
        register = CashRegister.all_objects.filter(
            restaurant=restaurant,
            opened_by=user,
            status__in=active_statuses,
        ).order_by("-opened_at").first()
        if register:
            if register.cash_station_id is None:
                register.cash_station = station
                register.station = station.name
                register.save(update_fields=["cash_station", "station", "updated_at"])
            return register
        station_in_use = CashRegister.all_objects.filter(
            restaurant=restaurant,
            cash_station=station,
            status__in=active_statuses,
        ).exists()
        operating_station = secondary if station_in_use and secondary is not None else station
        try:
            return open_cash_register(
                restaurant=restaurant,
                cash_station=operating_station,
                user=user,
                opening_amount=Decimal("920.00"),
                notes="seed:cash:current",
            )
        except ValidationError:
            return CashRegister.all_objects.filter(
                restaurant=restaurant,
                cash_station=operating_station,
                status__in=active_statuses,
            ).order_by("-opened_at").first()

    def _seed_closed_cash_session(self, branch, station, user):
        register = CashRegister.all_objects.filter(
            cash_station=station,
            notes="seed:cash:closed",
        ).first()
        closed_at = timezone.now() - timedelta(days=1, hours=2)
        opened_at = closed_at - timedelta(hours=8)
        if register is None:
            register = CashRegister.all_objects.create(
                account=station.account,
                restaurant=station.restaurant,
                branch=branch,
                cash_station=station,
                opened_by=user,
                closed_by=user,
                status=CashRegister.STATUS_CLOSED_DIFFERENCE,
                opening_amount=Decimal("300.00"),
                expected_amount=Decimal("925.00"),
                actual_amount=Decimal("920.00"),
                difference_amount=Decimal("-5.00"),
                station=station.name,
                notes="seed:cash:closed",
                opening_is_initial=False,
                approval_reason="Diferença de demonstração aprovada pelo gerente.",
                approved_by=user,
                approved_at=closed_at,
                created_by=user,
                updated_by=user,
            )
            CashRegister.all_objects.filter(pk=register.pk).update(
                opened_at=opened_at,
                closed_at=closed_at,
                created_at=opened_at,
                updated_at=closed_at,
            )
        rows = [
            ("seed-opening", CashMovement.TYPE_OPENING, Decimal("300.00"), "Abertura do caixa"),
            ("seed-sale", CashMovement.TYPE_SALE, Decimal("700.00"), "Vendas em dinheiro do período"),
            ("seed-supply", CashMovement.TYPE_SUPPLY, Decimal("100.00"), "Reforço de troco"),
            ("seed-withdrawal", CashMovement.TYPE_WITHDRAWAL, Decimal("-175.00"), "Sangria para o cofre"),
            ("seed-closing", CashMovement.TYPE_CLOSING, Decimal("0.00"), "Fechamento do caixa"),
        ]
        for index, (key, movement_type, amount, reason) in enumerate(rows):
            movement, _ = CashMovement.all_objects.update_or_create(
                account=station.account,
                cash_register=register,
                metadata__seed_key=key,
                defaults={
                    "restaurant": station.restaurant,
                    "branch": branch,
                    "operator": user,
                    "movement_type": movement_type,
                    "amount": amount,
                    "reason": reason,
                    "destination": "Cofre" if movement_type == CashMovement.TYPE_WITHDRAWAL else "",
                    "status": "approved",
                    "authorized_by": user if movement_type == CashMovement.TYPE_WITHDRAWAL else None,
                    "approved_at": opened_at + timedelta(hours=index + 1),
                    "metadata": {"seed_key": key, "source": "seed_demo"},
                    "created_by": user,
                    "updated_by": user,
                },
            )
            movement_time = opened_at + timedelta(hours=index + 1)
            CashMovement.all_objects.filter(pk=movement.pk).update(created_at=movement_time, updated_at=movement_time)

    def _seed_current_cash_movements(self, register, user):
        if register is None or register.status != CashRegister.STATUS_OPEN:
            return
        rows = [
            ("current-supply", CashMovement.TYPE_SUPPLY, Decimal("80.00"), "Suprimento para troco", "approved"),
            ("current-withdrawal", CashMovement.TYPE_WITHDRAWAL, Decimal("-120.00"), "Sangria aguardando gerente", "pending"),
        ]
        for key, movement_type, amount, reason, movement_status in rows:
            CashMovement.all_objects.update_or_create(
                account=register.account,
                cash_register=register,
                metadata__seed_key=key,
                defaults={
                    "restaurant": register.restaurant,
                    "branch": register.branch,
                    "operator": user,
                    "movement_type": movement_type,
                    "amount": amount,
                    "reason": reason,
                    "destination": "Cofre" if movement_type == CashMovement.TYPE_WITHDRAWAL else "",
                    "status": movement_status,
                    "metadata": {"seed_key": key, "source": "seed_demo"},
                    "created_by": user,
                    "updated_by": user,
                },
            )

    def _build_recipes(self, account, restaurant, branch, products, ingredients, recipes_data, user):
        for code, rows in recipes_data.items():
            recipe = self._upsert(
                Recipe,
                {"account": account, "restaurant": restaurant, "branch": branch, "product": products[code]},
                {"yield_quantity": Decimal("1"), "auto_deduct_stock": True, "is_active": True, "created_by": user, "updated_by": user},
            )
            total_cost = Decimal("0.00")
            for ingredient_name, quantity, unit in rows:
                ingredient = ingredients[ingredient_name]
                qty_d = Decimal(quantity)
                item_cost = (ingredient.average_cost * qty_d).quantize(Decimal("0.01"))
                total_cost += item_cost
                self._upsert(
                    RecipeItem,
                    {"account": account, "restaurant": restaurant, "branch": branch, "recipe": recipe, "ingredient": ingredient},
                    {"quantity": qty_d, "unit": unit, "ingredient_cost": ingredient.average_cost, "total_cost": item_cost, "created_by": user, "updated_by": user},
                )
            recipe.total_cost = total_cost
            recipe.save(update_fields=["total_cost", "updated_at"])

    def _build_customers(self, account, restaurant, branch, user, data):
        customers = {}
        for name, phone, email, street, number, district in data:
            customer = self._first_or_create(
                Customer,
                {"account": account, "restaurant": restaurant, "branch": branch, "phone": phone},
                {"name": name, "email": email, "document": "", "internal_notes": "Cliente demo.", "is_active": True, "created_by": user, "updated_by": user},
            )
            self._first_or_create(
                CustomerAddress,
                {"account": account, "restaurant": restaurant, "branch": branch, "customer": customer, "label": "Principal"},
                {"street": street, "number": number, "district": district, "city": "Rio de Janeiro", "state": "RJ", "zip_code": "20000-000", "reference": "Endereço demo.", "is_default": True, "created_by": user, "updated_by": user},
            )
            customers[name] = customer
        return customers

    def _dt(self, day, hour, minute):
        return timezone.make_aware(datetime.combine(day, time(hour, minute)), timezone.get_current_timezone())

    def _backfill_order(self, order, payment, opened_at, closed_at):
        Order.all_objects.filter(pk=order.pk).update(
            opened_at=opened_at, closed_at=closed_at, created_at=opened_at, updated_at=closed_at,
            production_status=Order.PROD_DELIVERED,
        )
        Payment.all_objects.filter(pk=payment.pk).update(paid_at=closed_at, created_at=closed_at, updated_at=closed_at)
        CashMovement.all_objects.filter(payment=payment).update(created_at=closed_at, updated_at=closed_at)
        OrderItem.all_objects.filter(order=order).update(status=OrderItem.STATUS_DELIVERED, delivered_at=closed_at, updated_at=closed_at)

    def _upsert(self, model, lookup, defaults):
        obj, _ = model.all_objects.update_or_create(**lookup, defaults=defaults)
        return obj

    def _first_or_create(self, model, lookup, defaults):
        obj = model.all_objects.filter(**lookup).first()
        if obj is None:
            return model.all_objects.create(**{**lookup, **defaults})
        changed = [f for f, v in defaults.items() if getattr(obj, f) != v and (setattr(obj, f, v) or True)]
        if changed:
            obj.save(update_fields=changed + ["updated_at"])
        return obj

    def _reset_sqlite_database(self):
        database = settings.DATABASES["default"]
        if database["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError("--reset-sqlite só funciona com SQLite.")
        db_name = database["NAME"]
        if db_name == ":memory:":
            raise CommandError("--reset-sqlite não suporta banco em memória.")
        db_path = Path(db_name)
        connection.close()
        if not db_path.exists():
            self.stdout.write(self.style.NOTICE(f"Banco SQLite ainda não existe: {db_path}"))
            return
        timestamp = timezone.now().strftime("%Y%m%d%H%M%S")
        backup_path = db_path.with_name(f"{db_path.stem}.{timestamp}.bak{db_path.suffix}")
        db_path.replace(backup_path)
        journal_path = db_path.with_name(f"{db_path.name}-journal")
        if journal_path.exists():
            journal_path.replace(backup_path.with_name(f"{backup_path.name}-journal"))
        self.stdout.write(self.style.WARNING(f"Banco SQLite salvo em: {backup_path}"))
