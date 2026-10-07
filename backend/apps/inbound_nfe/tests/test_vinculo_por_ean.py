"""Vínculo pelo EAN na nota de entrada.

O EAN igual ao do cadastro ganhava nota 0,95 — e só 1,0 é aplicado sozinho:
na prática NUNCA vinculava automático. E procurava só no campo antigo
`gtin`, não no `ean` do produto. No vínculo manual, o EAN da nota passa a ir
para o produto que ainda não tem nenhum.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem
from apps.inbound_nfe.services.matching import apply_mapping_to_item
from apps.menu.models import Product, ProductCategory
from apps.restaurants.models import Restaurant

User = get_user_model()
CNPJ = "98765432000188"
EAN = "7894900011517"


class VinculoPorEanTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(name="Conta EAN", slug="conta-ean", document="12345678000199")
        self.restaurant = Restaurant.objects.create(
            account=self.account, trade_name="Loja", legal_name="Loja LTDA", cnpj="12345678000199",
        )
        self.categoria = ProductCategory.objects.create(account=self.account, restaurant=self.restaurant, name="Bebidas")
        self.invoice = InboundNFe.objects.create(
            account=self.account, restaurant=self.restaurant,
            access_key="35260812345678000199550010000000011000000099", number="9", series="1",
            supplier_name="Fornecedor", supplier_cnpj=CNPJ, issue_date=timezone.now(),
            status=InboundNFe.STATUS_PENDING_MAPPING,
        )
        user = User.objects.create_superuser("ean", "e@starchef.app", "senha123")
        self.client = APIClient(HTTP_X_ACCOUNT_ID=str(self.account.id))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")

    def _produto(self, nome, **extra):
        return Product.objects.create(
            account=self.account, restaurant=self.restaurant, category=self.categoria,
            name=nome, sale_price=Decimal("6"), stock_unit="UN", **extra,
        )

    def _item(self, ean=EAN, numero=1):
        return InboundNFeItem.objects.create(
            account=self.account, invoice=self.invoice, item_number=numero, ean=ean,
            supplier_code=f"C{numero}", description="COCA COLA LT 350",
            commercial_quantity=Decimal("1"), commercial_unit="UN",
            commercial_unit_value=Decimal("3"), product_total=Decimal("3"),
        )

    def test_ean_igual_ao_do_cadastro_vincula_sozinho(self):
        produto = self._produto("Coca-Cola Lata", ean=EAN)
        item = self._item()

        apply_mapping_to_item(item, CNPJ)

        item.refresh_from_db()
        self.assertEqual(item.product_id, produto.id)

    def test_ean_no_campo_antigo_gtin_tambem_vincula(self):
        produto = self._produto("Coca-Cola Lata", gtin=EAN)
        item = self._item()

        apply_mapping_to_item(item, CNPJ)

        item.refresh_from_db()
        self.assertEqual(item.product_id, produto.id)

    def test_dois_produtos_com_o_mesmo_ean_nao_vinculam_sozinhos(self):
        """Na dúvida, quem decide é a pessoa: vincular errado entra estoque no produto errado."""
        # `ean` é único na conta; a duplicidade real é o mesmo código no
        # campo antigo `gtin` de outro produto.
        self._produto("Coca-Cola Lata", ean=EAN)
        self._produto("Coca-Cola Lata (cadastro antigo)", gtin=EAN)
        item = self._item()

        apply_mapping_to_item(item, CNPJ)

        item.refresh_from_db()
        self.assertIsNone(item.product_id)

    def test_sem_gtin_nao_vincula_nada(self):
        self._produto("Sem código", ean="SEM GTIN")
        item = self._item(ean="SEM GTIN")

        apply_mapping_to_item(item, CNPJ)

        item.refresh_from_db()
        self.assertIsNone(item.product_id)

    def test_vinculo_manual_grava_o_ean_da_nota_no_produto_sem_ean(self):
        produto = self._produto("Coca-Cola Lata")
        item = self._item()

        resposta = self.client.post(
            f"/api/v1/inbound-nfe-items/{item.id}/map/", {"product_id": str(produto.id)}, format="json",
        )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        produto.refresh_from_db()
        self.assertEqual(produto.ean, EAN)

    def test_vinculo_manual_nao_sobrescreve_o_ean_que_o_produto_ja_tem(self):
        produto = self._produto("Coca-Cola Lata", ean="7890000000017")
        item = self._item()

        self.client.post(
            f"/api/v1/inbound-nfe-items/{item.id}/map/", {"product_id": str(produto.id)}, format="json",
        )

        produto.refresh_from_db()
        self.assertEqual(produto.ean, "7890000000017")

    def test_vinculo_manual_nao_grava_ean_que_outro_produto_ja_usa(self):
        """O `ean` é único na conta: gravar estouraria o vínculo inteiro."""
        self._produto("Dono do código", ean=EAN)
        produto = self._produto("Coca-Cola Lata (outra)")
        item = self._item()

        resposta = self.client.post(
            f"/api/v1/inbound-nfe-items/{item.id}/map/", {"product_id": str(produto.id)}, format="json",
        )

        self.assertEqual(resposta.status_code, 200, resposta.data)
        produto.refresh_from_db()
        self.assertEqual(produto.ean or "", "")
