"""Desfazer o "Vincular Produto" de um item da NF-e de entrada."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, SupplierItemMapping
from apps.inbound_nfe.services.matching import apply_mapping_to_item
from apps.menu.models import Ingredient, Product, ProductCategory, ProductUnitConversion
from apps.restaurants.models import Restaurant

User = get_user_model()
CNPJ_FORNECEDOR = "98765432000188"


class DesvincularItemTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Conta Vinculo", slug="conta-vinculo", document="12345678000199"
        )
        self.restaurant = Restaurant.objects.create(
            account=self.account, trade_name="Loja", legal_name="Loja LTDA",
            cnpj="12345678000199",
        )
        categoria = ProductCategory.objects.create(
            account=self.account, restaurant=self.restaurant, name="Bebidas"
        )
        base = {"account": self.account, "restaurant": self.restaurant,
                "category": categoria, "sale_price": Decimal("6"), "stock_unit": "UN"}
        self.errado = Product.objects.create(name="Guaraná Lata", **base)
        self.certo = Product.objects.create(name="Refrigerante Cola Lata", **base)
        user = User.objects.create_superuser("vinculo", "v@starchef.app", "senha123")
        self.client = APIClient(HTTP_X_ACCOUNT_ID=str(self.account.id))
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.invoice = InboundNFe.objects.create(
            account=self.account, restaurant=self.restaurant,
            access_key="35260812345678000199550010000000011000000011",
            number="1", series="1", supplier_name="Fornecedor ABC",
            supplier_cnpj=CNPJ_FORNECEDOR, issue_date=timezone.now(),
            status=InboundNFe.STATUS_PENDING_MAPPING,
        )
        self.item = InboundNFeItem.objects.create(
            account=self.account, invoice=self.invoice, item_number=1,
            supplier_code="REF-01", description="REFRI COLA LT 350 CX12",
            commercial_quantity=Decimal("2"), commercial_unit="CX",
            commercial_unit_value=Decimal("30"), product_total=Decimal("60"),
        )

    def _vincular(self, produto, fator="12"):
        return self.client.post(
            f"/api/v1/inbound-nfe-items/{self.item.id}/map/",
            {"product_id": str(produto.id), "conversion_factor": fator},
            format="json",
        )

    def test_desvincular_apaga_o_item_e_o_aprendizado_errado_e_permite_refazer(self):
        """Sem esquecer o aprendizado, a próxima nota do fornecedor voltaria
        vinculada ao produto errado sozinha."""
        self.assertEqual(self._vincular(self.errado).status_code, 200)
        self.assertTrue(SupplierItemMapping.all_objects.filter(product=self.errado).exists())
        self.assertTrue(ProductUnitConversion.all_objects.filter(product=self.errado).exists())

        resposta = self.client.post(f"/api/v1/inbound-nfe-items/{self.item.id}/unlink/")

        self.assertEqual(resposta.status_code, 200, resposta.data)
        self.item.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertIsNone(self.item.product_id)
        self.assertEqual(self.item.conversion_factor, 1)
        self.assertEqual(self.invoice.status, InboundNFe.STATUS_PENDING_MAPPING)
        self.assertFalse(SupplierItemMapping.all_objects.filter(product=self.errado).exists())
        self.assertFalse(ProductUnitConversion.all_objects.filter(product=self.errado).exists())

        self.assertEqual(self._vincular(self.certo).status_code, 200)
        aprendido = SupplierItemMapping.all_objects.get(
            supplier_cnpj=CNPJ_FORNECEDOR, supplier_code="REF-01"
        )
        self.assertEqual(aprendido.product, self.certo)

    def test_desvincular_sem_esquecer_mantem_o_aprendizado(self):
        self._vincular(self.errado)

        self.client.post(
            f"/api/v1/inbound-nfe-items/{self.item.id}/unlink/",
            {"forget_supplier_mapping": False}, format="json",
        )

        self.assertTrue(SupplierItemMapping.all_objects.filter(product=self.errado).exists())

    def test_nota_recebida_recusa_desvincular_e_trocar_o_vinculo_com_409(self):
        """Depois da entrada no estoque, trocar o vínculo deixaria a nota
        apontando para um produto e o estoque em outro."""
        self._vincular(self.errado)
        InboundNFe.all_objects.filter(pk=self.invoice.pk).update(status=InboundNFe.STATUS_RECEIVED)

        desvincular = self.client.post(f"/api/v1/inbound-nfe-items/{self.item.id}/unlink/")
        trocar = self._vincular(self.certo)

        self.assertEqual(desvincular.status_code, 409)
        self.assertEqual(trocar.status_code, 409)
        self.item.refresh_from_db()
        self.assertEqual(self.item.product, self.errado)

    def _insumo(self):
        insumo = Ingredient.objects.create(
            account=self.account, restaurant=self.restaurant, name="FANTA LARANJA CX24"
        )
        self.client.post(
            f"/api/v1/inbound-nfe-items/{self.item.id}/map/",
            {"ingredient_id": str(insumo.id), "conversion_factor": "24"}, format="json",
        )
        return insumo

    def test_excluir_o_insumo_solta_a_nota_pendente_e_esquece_o_aprendizado(self):
        """Excluir é só `deleted_at`: o item seguia "Ingrediente: X" e a próxima
        nota do fornecedor voltava ligada ao insumo apagado."""
        insumo = self._insumo()

        insumo.delete()

        self.item.refresh_from_db()
        self.invoice.refresh_from_db()
        self.assertIsNone(self.item.ingredient_id)
        self.assertEqual(self.invoice.status, InboundNFe.STATUS_PENDING_MAPPING)
        self.assertFalse(SupplierItemMapping.all_objects.filter(ingredient=insumo).exists())

    def test_nota_recebida_mantem_o_vinculo_quando_o_insumo_e_excluido(self):
        insumo = self._insumo()
        InboundNFe.all_objects.filter(pk=self.invoice.pk).update(status=InboundNFe.STATUS_RECEIVED)

        insumo.delete()

        self.item.refresh_from_db()
        self.assertEqual(self.item.ingredient_id, insumo.id)

    def test_aprendizado_que_aponta_para_insumo_excluido_nao_religa_nota_nova(self):
        insumo = self._insumo()
        # Exclusão por fora do sinal (dado antigo, de antes desta correção).
        Ingredient.all_objects.filter(pk=insumo.pk).update(deleted_at=timezone.now())
        novo = InboundNFeItem.objects.create(
            account=self.account, invoice=self.invoice, item_number=2,
            supplier_code="REF-01", description="REFRI COLA LT 350 CX12",
        )

        apply_mapping_to_item(novo, CNPJ_FORNECEDOR)

        novo.refresh_from_db()
        self.assertIsNone(novo.ingredient_id)

    def test_migracao_reativa_o_insumo_preso_menos_quando_o_nome_ja_foi_reusado(self):
        """O insumo apagado antes da correção volta, para ser excluído de novo
        pelo caminho certo; o que teria o nome em conflito fica apagado."""
        import importlib

        from django.db import connection
        from django.db.migrations.loader import MigrationLoader

        migracao = importlib.import_module(
            "apps.inbound_nfe.migrations.0010_reativa_insumos_presos_a_nfe"
        )
        insumo = self._insumo()
        Ingredient.all_objects.filter(pk=insumo.pk).update(deleted_at=timezone.now())
        outro = Ingredient.objects.create(account=self.account, name="SPRITE CX24")
        SupplierItemMapping.all_objects.create(
            account=self.account, restaurant=self.restaurant, supplier_cnpj=CNPJ_FORNECEDOR,
            supplier_code="SPR-01", ingredient=outro,
        )
        Ingredient.all_objects.filter(pk=outro.pk).update(deleted_at=timezone.now())
        Ingredient.objects.create(account=self.account, name="SPRITE CX24")

        # Os models HISTÓRICOS, como o `migrate` entrega: os atuais filtram pela
        # conta do contexto e enxergariam uma lista vazia.
        estado = MigrationLoader(connection).project_state(
            ("inbound_nfe", "0010_reativa_insumos_presos_a_nfe")
        )
        migracao.desfazer(estado.apps, None)

        insumo.refresh_from_db()
        outro.refresh_from_db()
        self.assertIsNone(insumo.deleted_at)
        self.assertIsNotNone(outro.deleted_at)
