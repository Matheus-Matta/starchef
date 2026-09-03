import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import Account
from apps.assets.models import Asset, AssetDisposal, AssetLocationHistory
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, SupplierItemMapping
from apps.inbound_nfe.services.receiving import receive_invoice
from apps.menu.models import Product, ProductCategory
from apps.restaurants.models import Branch, Restaurant
from apps.stock.models import (
    GoodsReceipt,
    GoodsReceiptItem,
    InventoryLot,
    StockLocation,
    StockMovement,
)
from apps.stock.services.fefo import consume_stock_fefo

User = get_user_model()


class InboundNFeCompleteFlowTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Conta Teste Gastronomia",
            slug="teste-gastronomia",
            document="12345678000199",
        )
        self.restaurant = Restaurant.objects.create(
            account=self.account,
            trade_name="Restaurante StarChef Gourmet",
            legal_name="Restaurante StarChef Gourmet LTDA",
            cnpj="12345678000199",
        )
        self.branch = Branch.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            name="Matriz",
        )
        self.user = User.objects.create_superuser(
            username="cheftest",
            email="chef@starchef.app",
            password="password123",
        )
        self.storage_location = StockLocation.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            name="Estoque Central",
            location_type=StockLocation.TYPE_STORAGE,
        )
        self.kitchen_location = StockLocation.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            name="Cozinha Principal",
            location_type=StockLocation.TYPE_KITCHEN,
        )
        self.category = ProductCategory.objects.create(
            account=self.account,
            branch=self.branch,
            name="Alimentos",
        )

    def test_01_ingredient_lot_and_fefo_consumption(self):
        """Teste 1: Insumo com Lote, Validade e consumo prioritário por FEFO."""
        picanha = Product.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            name="Picanha Bovina Resfriada",
            internal_code="PIC-001",
            gtin="7891234567890",
            category=self.category,
            item_type=Product.ITEM_INGREDIENT,
            tracking_mode=Product.TRACKING_LOT,
            stock_unit="KG",
            sale_price=Decimal("89.90"),
            requires_lot_control=True,
            requires_expiration_control=True,
        )

        nfe = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            access_key="33260808969770000159550010054463751287194801",
            number="1001",
            series="1",
            supplier_cnpj="08969770000159",
            supplier_name="FRIGORIFICO FORNECEDOR S/A",
            total_products=Decimal("958.00"),
            total_invoice=Decimal("958.00"),
            status=InboundNFe.STATUS_PENDING_RECEIPT,
        )
        nfe_item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            invoice=nfe,
            item_number=1,
            supplier_code="CARNE-001",
            ean="7891234567890",
            description="PICANHA BOVINA RESFRIADA A VACUO",
            commercial_unit="KG",
            commercial_quantity=Decimal("20.000"),
            commercial_unit_value=Decimal("47.90"),
            product_total=Decimal("958.00"),
            product=picanha,
            conversion_factor=Decimal("1"),
        )

        today = datetime.date.today()
        exp_date = today + datetime.timedelta(days=15)

        receipt = receive_invoice(
            invoice_id=nfe.id,
            user=self.user,
            location=self.storage_location,
            items_data=[
                {
                    "item_id": str(nfe_item.id),
                    "received_quantity": Decimal("19.800"),  # Divergência de 200g
                    "accepted_quantity": Decimal("19.800"),
                    "lot_number": "LOTE-PIC-2026-A",
                    "expiration_date": exp_date,
                    "manufacturing_date": today,
                }
            ],
            receipt_notes="Conferido e pesado na recepção.",
        )

        # Validação do recebimento e divergência
        self.assertEqual(receipt.status, GoodsReceipt.STATUS_DIVERGENT)
        self.assertEqual(GoodsReceiptItem.all_objects.filter(receipt=receipt).count(), 1)
        receipt_item = GoodsReceiptItem.all_objects.filter(receipt=receipt).first()
        self.assertEqual(receipt_item.expected_quantity, Decimal("20.000"))
        self.assertEqual(receipt_item.received_quantity, Decimal("19.800"))
        self.assertEqual(receipt_item.difference_quantity, Decimal("-0.200"))

        # Validação do Lote
        lot = InventoryLot.all_objects.filter(product=picanha).first()
        self.assertIsNotNone(lot)
        self.assertEqual(lot.lot_number, "LOTE-PIC-2026-A")
        self.assertEqual(lot.available_quantity, Decimal("19.800"))
        self.assertEqual(lot.status, InventoryLot.STATUS_ACTIVE)

        # Validação do Movimento de Estoque
        movement = StockMovement.all_objects.filter(product=picanha).first()
        self.assertIsNotNone(movement)
        self.assertEqual(movement.movement_type, StockMovement.TYPE_PURCHASE_ENTRY)
        self.assertEqual(movement.quantity, Decimal("19.800"))

        # Validação do Custo Médio Atualizado
        picanha.refresh_from_db()
        self.assertGreater(picanha.current_average_cost, Decimal("0"))

        # Consumo por FEFO (ex: venda de 5kg)
        consumed = consume_stock_fefo(
            account=self.account,
            product=picanha,
            location=self.storage_location,
            quantity=Decimal("5.000"),
            operator=self.user,
            reason="Venda Comanda #12",
        )
        self.assertEqual(len(consumed), 1)
        lot.refresh_from_db()
        self.assertEqual(lot.available_quantity, Decimal("14.800"))

    def test_02_reusable_utensil_and_breakage(self):
        """Teste 2: Material Reutilizável (Pratos) — entrada quantitativa e registro de quebra."""
        prato = Product.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            name="Prato Raso Porcelana 27cm",
            internal_code="UT-PRATO-01",
            category=self.category,
            item_type=Product.ITEM_REUSABLE,
            tracking_mode=Product.TRACKING_QUANTITY,
            stock_unit="UN",
            sale_price=Decimal("0.00"),
        )

        nfe = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            access_key="33260808969770000159550010054463751287194802",
            number="1002",
            supplier_cnpj="11222333000144",
            supplier_name="DISTRIBUIDORA DE UTENSILIOS LTDA",
            total_products=Decimal("1800.00"),
            total_invoice=Decimal("1800.00"),
            status=InboundNFe.STATUS_PENDING_RECEIPT,
        )
        nfe_item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            invoice=nfe,
            item_number=1,
            supplier_code="PRATO-27",
            description="PRATO PORCELANA BRANCO 27CM",
            commercial_unit="UN",
            commercial_quantity=Decimal("100.000"),
            commercial_unit_value=Decimal("18.00"),
            product_total=Decimal("1800.00"),
            product=prato,
            conversion_factor=Decimal("1"),
        )

        receive_invoice(
            invoice_id=nfe.id,
            user=self.user,
            location=self.storage_location,
            items_data=[
                {
                    "item_id": str(nfe_item.id),
                    "received_quantity": Decimal("100.000"),
                }
            ],
        )

        # Não deve criar patrimônio serializado
        self.assertEqual(Asset.all_objects.filter(product=prato).count(), 0)

        # Saldo inicial = 100
        balance = StockMovement.all_objects.filter(product=prato).first().quantity
        self.assertEqual(balance, Decimal("100.000"))

        # Registro de Quebra de 2 pratos
        breakage_movement = StockMovement.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            product=prato,
            location=self.storage_location,
            operator=self.user,
            movement_type=StockMovement.TYPE_BREAKAGE,
            quantity=Decimal("-2.000"),
            stock_unit="UN",
            unit_cost=prato.current_average_cost,
            total_cost=Decimal("2.000") * prato.current_average_cost,
            reason="Queda na lavagem de louças",
        )
        self.assertEqual(breakage_movement.movement_type, StockMovement.TYPE_BREAKAGE)

    def test_03_serialized_equipment_asset_creation_and_transfer(self):
        """Teste 3: Equipamento Serializado — gera instâncias de Asset com garantia e histórico."""
        freezer = Product.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            name="Freezer Horizontal Metalfrio 500L",
            internal_code="EQ-FREEZER-500",
            category=self.category,
            brand="Metalfrio",
            model="DA550",
            item_type=Product.ITEM_EQUIPMENT,
            tracking_mode=Product.TRACKING_SERIALIZED,
            stock_unit="UN",
            default_useful_life_months=24,
            requires_serial_number=True,
            requires_maintenance=True,
        )

        nfe = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            access_key="33260808969770000159550010054463751287194803",
            number="8521",
            supplier_cnpj="99888777000100",
            supplier_name="REFRIGERACAO INDUSTRIAL BRASIL LTDA",
            total_products=Decimal("11600.00"),
            total_invoice=Decimal("11600.00"),
            status=InboundNFe.STATUS_PENDING_RECEIPT,
        )
        nfe_item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            invoice=nfe,
            item_number=1,
            supplier_code="MET-500L",
            description="FREEZER HORIZONTAL 500L 220V",
            commercial_unit="UN",
            commercial_quantity=Decimal("2.000"),
            commercial_unit_value=Decimal("5800.00"),
            product_total=Decimal("11600.00"),
            product=freezer,
            conversion_factor=Decimal("1"),
        )

        receive_invoice(
            invoice_id=nfe.id,
            user=self.user,
            location=self.storage_location,
            items_data=[
                {
                    "item_id": str(nfe_item.id),
                    "received_quantity": Decimal("2.000"),
                    "serials": ["META-2026-001", "META-2026-002"],
                }
            ],
        )

        # Devem ter sido criados exatamente 2 registros de Asset
        assets = list(Asset.all_objects.filter(product=freezer).order_by("asset_code"))
        self.assertEqual(len(assets), 2)

        asset1, asset2 = assets[0], assets[1]
        self.assertEqual(asset1.serial_number, "META-2026-001")
        self.assertEqual(asset2.serial_number, "META-2026-002")
        self.assertEqual(asset1.purchase_price, Decimal("5800.00"))
        self.assertEqual(asset1.status, Asset.STATUS_IN_USE)
        self.assertIsNotNone(asset1.warranty_end_date)
        self.assertIsNotNone(asset1.qr_code_token)

        # Histórico de localização inicial
        self.assertEqual(AssetLocationHistory.all_objects.filter(asset=asset1).count(), 1)

        # Transferência de local (Estoque -> Cozinha)
        old_location = asset1.location
        asset1.location = self.kitchen_location
        asset1.save()

        AssetLocationHistory.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            asset=asset1,
            from_location=old_location,
            to_location=self.kitchen_location,
            moved_by=self.user,
            reason="Instalação na linha de produção da cozinha",
        )

        self.assertEqual(AssetLocationHistory.all_objects.filter(asset=asset1).count(), 2)

        # Baixa patrimonial do asset2
        asset2.status = Asset.STATUS_DISPOSED
        asset2.save()
        AssetDisposal.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            branch=self.branch,
            asset=asset2,
            disposal_type=AssetDisposal.DISPOSAL_SCRAPPED,
            authorized_by=self.user,
            reason="Avaria irrecuperável de compressor",
        )
        self.assertTrue(hasattr(asset2, "disposal"))
        self.assertEqual(asset2.disposal.disposal_type, AssetDisposal.DISPOSAL_SCRAPPED)
