import datetime
from decimal import Decimal
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem
from apps.inbound_nfe.services.receiving import receive_invoice
from apps.menu.models import Product, ProductCategory
from apps.restaurants.models import Branch, Restaurant
from apps.stock.models import StockLocation, StockMovement

User = get_user_model()


class InboundNFeIgnoreTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Conta Teste Ignorar",
            slug="teste-ignorar",
            document="12345678000199",
        )
        self.restaurant = Restaurant.objects.create(
            account=self.account,
            trade_name="Restaurante Teste",
            legal_name="Restaurante Teste LTDA",
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
        self.category = ProductCategory.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            name="Bebidas",
        )
        self.product = Product.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            name="Refrigerante Cola Lata",
            category=self.category,
            sale_price=Decimal("6.00"),
            stock_unit="UN",
            controls_stock=True,
        )

        # Superusuario atua no escopo informado explicitamente; a API nunca
        # abre acesso global a todas as contas.
        self.client = APIClient(HTTP_X_ACCOUNT_ID=str(self.account.id))
        access = str(RefreshToken.for_user(self.user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    def _create_invoice(self, access_key="35260812345678000199550010000000011000000011", number="1"):
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key=access_key,
            number=number,
            series="1",
            supplier_name="Fornecedor ABC LTDA",
            supplier_cnpj="98765432000188",
            issue_date=datetime.date.today(),
            total_invoice=Decimal("150.00"),
            total_products=Decimal("150.00"),
            status=InboundNFe.STATUS_PENDING_MAPPING,
        )
        item1 = InboundNFeItem.objects.create(
            account=self.account,
            invoice=invoice,
            item_number=1,
            supplier_code="REF-01",
            description="Refrigerante Cola 350ml",
            commercial_quantity=Decimal("10.0000"),
            commercial_unit="UN",
            commercial_unit_value=Decimal("5.0000"),
            product_total=Decimal("50.00"),
        )
        item2 = InboundNFeItem.objects.create(
            account=self.account,
            invoice=invoice,
            item_number=2,
            supplier_code="BRINDE-01",
            description="Brinde Promocional / Amostra",
            commercial_quantity=Decimal("5.0000"),
            commercial_unit="UN",
            commercial_unit_value=Decimal("20.0000"),
            product_total=Decimal("100.00"),
        )
        return invoice, item1, item2

    def test_ignore_and_unignore_invoice(self):
        invoice, item1, item2 = self._create_invoice()

        # 1. Ignorar nota inteira via API
        response = self.client.post(
            f"/api/v1/inbound-nfe/{invoice.id}/ignore/",
            {"reason": "Nota fiscal de teste que não será estocada"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_IGNORED)
        self.assertIsNotNone(invoice.ignored_at)
        self.assertEqual(invoice.ignored_reason, "Nota fiscal de teste que não será estocada")
        self.assertEqual(invoice.ignored_by, self.user)

        # 2. Status counts deve incluir "ignored"
        counts_resp = self.client.get("/api/v1/inbound-nfe/status-counts/")
        self.assertEqual(counts_resp.status_code, 200)
        self.assertGreaterEqual(counts_resp.data.get("ignored", 0), 1)

        # 3. Reativar nota via API
        unignore_resp = self.client.post(f"/api/v1/inbound-nfe/{invoice.id}/unignore/")
        self.assertEqual(unignore_resp.status_code, 200)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_PENDING_MAPPING)
        self.assertIsNone(invoice.ignored_at)
        self.assertEqual(invoice.ignored_reason, "")
        self.assertIsNone(invoice.ignored_by)

    def test_bulk_ignore_invoices(self):
        inv1, _, _ = self._create_invoice("35260812345678000199550010000000021000000022", number="2")
        inv2, _, _ = self._create_invoice("35260812345678000199550010000000031000000033", number="3")

        response = self.client.post(
            "/api/v1/inbound-nfe/bulk-ignore/",
            {"ids": [inv1.id, inv2.id], "reason": "Ignoradas em lote"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data.get("updated_count"), 2)

        inv1.refresh_from_db()
        inv2.refresh_from_db()
        self.assertEqual(inv1.status, InboundNFe.STATUS_IGNORED)
        self.assertEqual(inv2.status, InboundNFe.STATUS_IGNORED)

    def test_ignore_item_partial_and_receive(self):
        invoice, item1, item2 = self._create_invoice()

        # Vincular apenas item1
        item1.product = self.product
        item1.conversion_factor = Decimal("1.0000")
        item1.save()

        # item2 não vinculado -> nota ainda pendente de mapeamento
        # Ignorar o item2 (ex: brinde que não vai pro estoque)
        response = self.client.post(
            f"/api/v1/inbound-nfe-items/{item2.id}/ignore/",
            {"reason": "Brinde não estocável"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)

        item2.refresh_from_db()
        self.assertTrue(item2.is_ignored)
        self.assertEqual(item2.ignored_reason, "Brinde não estocável")

        # Como o único item ativo restante (item1) já está mapeado,
        # a nota deve ter sido automaticamente promovida para pending_receipt!
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_PENDING_RECEIPT)

        # Dar entrada no estoque via receive_invoice
        receipt_data = receive_invoice(
            invoice=invoice,
            received_by=self.user,
            location=self.storage_location,
            items_payload=[
                {
                    "item_id": item1.id,
                    "received_quantity": Decimal("10.0000"),
                    "accepted_quantity": Decimal("10.0000"),
                },
                # Mesmo se payload passar item2, o serviço deve ignorá-lo
                {
                    "item_id": item2.id,
                    "received_quantity": Decimal("5.0000"),
                    "accepted_quantity": Decimal("5.0000"),
                },
            ],
            notes="Entrada com itens ignorados",
        )

        # Apenas movimentação de estoque para item1 deve ter sido criada
        movements = StockMovement.all_objects.filter(account=self.account, product=self.product)
        self.assertEqual(movements.count(), 1)
        self.assertEqual(movements.first().quantity, Decimal("10.0000"))

        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_RECEIVED)

    def test_ignore_all_items_marks_invoice_as_ignored(self):
        invoice, item1, item2 = self._create_invoice()

        # Ignorar item1
        self.client.post(f"/api/v1/inbound-nfe-items/{item1.id}/ignore/")
        invoice.refresh_from_db()
        self.assertNotEqual(invoice.status, InboundNFe.STATUS_IGNORED)

        # Ignorar item2 -> agora todos os itens estão ignorados!
        self.client.post(f"/api/v1/inbound-nfe-items/{item2.id}/ignore/")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_IGNORED)

        # Reativar item1 -> nota volta a ser ativa (pending_mapping)
        self.client.post(f"/api/v1/inbound-nfe-items/{item1.id}/unignore/")
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, InboundNFe.STATUS_PENDING_MAPPING)
