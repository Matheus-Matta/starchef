"""
Testes automatizados para o tratamento e estorno de NF-e cancelada.
Cobre o parser de eventos, aplicação de cancelamento com reversão imutável de estoque,
tratamento de patrimônio e bloqueios operacionais.
"""

from decimal import Decimal
from django.test import TestCase
from apps.accounts.models import Account
from apps.restaurants.models import Restaurant
from apps.menu.models import Product
from apps.stock.models import StockLocation, StockMovement, GoodsReceipt
from apps.assets.models import Asset
from django.contrib.auth import get_user_model
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, NFeIssue
from apps.inbound_nfe.services.event_parser import parse_nfe_event
from apps.inbound_nfe.services.cancellation import apply_cancellation
from apps.inbound_nfe.services.status_query import parse_and_apply_cons_sit_response

User = get_user_model()


class NFeCancellationFlowTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Conta Teste",
            slug="conta-teste-cancel",
            document="08824171000147",
        )
        self.user = User.objects.create_user(
            username="operador",
            email="operador@starchef.com.br",
            password="password123",
        )
        self.restaurant = Restaurant.objects.create(
            account=self.account,
            trade_name="Restaurante Teste",
            legal_name="Restaurante Teste LTDA",
            cnpj="08824171000147",
        )
        self.location = StockLocation.objects.create(
            name="Depósito Central",
            account=self.account,
            restaurant=self.restaurant,
        )
        self.product = Product.objects.create(
            name="Água Mineral 500ml",
            account=self.account,
            restaurant=self.restaurant,
            stock_unit="UN",
            current_average_cost=Decimal("2.00"),
            sale_price=Decimal("5.00"),
        )
        self.asset_product = Product.objects.create(
            name="Geladeira Comercial",
            account=self.account,
            restaurant=self.restaurant,
            stock_unit="UN",
            item_type=Product.ITEM_EQUIPMENT,
            tracking_mode=Product.TRACKING_SERIALIZED,
            requires_serial_number=True,
        )

    def test_parse_proc_evento_cancellation(self):
        """Valida que o parser de procEventoNFe extrai corretamente dados de cancelamento."""
        xml = """<procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
          <evento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
            <infEvento Id="ID1101113326080007456900478455010002095756191482915301">
              <cOrgao>33</cOrgao>
              <tpAmb>1</tpAmb>
              <CNPJ>00074569004784</CNPJ>
              <chNFe>33260800074569004784550100020957561914829153</chNFe>
              <dhEvento>2026-08-31T15:30:00-03:00</dhEvento>
              <tpEvento>110111</tpEvento>
              <nSeqEvento>1</nSeqEvento>
              <detEvento versao="1.00">
                <descEvento>Cancelamento</descEvento>
                <nProt>233260409351985</nProt>
                <xJust>Erro nos valores faturados</xJust>
              </detEvento>
            </infEvento>
          </evento>
          <retEvento versao="1.00" xmlns="http://www.portalfiscal.inf.br/nfe">
            <infEvento>
              <cStat>135</cStat>
              <xMotivo>Evento registrado e vinculado a NF-e</xMotivo>
              <chNFe>33260800074569004784550100020957561914829153</chNFe>
              <dhRegEvento>2026-08-31T15:31:00-03:00</dhRegEvento>
              <nProt>133260000012345</nProt>
            </infEvento>
          </retEvento>
        </procEventoNFe>"""

        parsed = parse_nfe_event(xml)
        self.assertEqual(parsed.access_key, "33260800074569004784550100020957561914829153")
        self.assertEqual(parsed.event_code, "110111")
        self.assertTrue(parsed.is_cancellation)
        self.assertTrue(parsed.is_effective_cancellation)
        self.assertEqual(parsed.protocol, "133260000012345")
        self.assertEqual(parsed.cancellation_reason, "Erro nos valores faturados")

    def test_apply_cancellation_before_receipt(self):
        """Se a NF-e ainda não foi recebida, marca como cancelada sem movimentações."""
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="33260800074569004784550100020957561914829153",
            number="2095756",
            series="1",
            status=InboundNFe.STATUS_PENDING_MAPPING,
            fiscal_status=InboundNFe.FISCAL_AUTHORIZED,
        )

        res = apply_cancellation(
            invoice=invoice,
            protocol="133260000012345",
            reason="Cancelamento pelo emitente",
        )

        invoice.refresh_from_db()
        self.assertEqual(invoice.fiscal_status, InboundNFe.FISCAL_CANCELLED)
        self.assertEqual(invoice.status, InboundNFe.STATUS_CANCELLED)
        self.assertEqual(invoice.cancellation_protocol, "133260000012345")
        self.assertEqual(res["reversals_created"], 0)
        self.assertEqual(StockMovement.objects.count(), 0)

    def test_apply_cancellation_after_receipt_reverses_stock(self):
        """Se a NF-e já gerou estoque, realiza estorno com TYPE_NFE_CANCELLATION_REVERSAL."""
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="33260800074569004784550100020957561914829153",
            number="2095756",
            series="1",
            status=InboundNFe.STATUS_RECEIVED,
            fiscal_status=InboundNFe.FISCAL_AUTHORIZED,
        )
        item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            invoice=invoice,
            item_number=1,
            description="Água Mineral",
            commercial_quantity=Decimal("20.00"),
            commercial_unit_value=Decimal("2.00"),
            product_total=Decimal("40.00"),
            product=self.product,
            conversion_factor=Decimal("1"),
            received_quantity=Decimal("20.00"),
        )
        receipt = GoodsReceipt.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            invoice=invoice,
            receipt_number="REC-000001",
            received_by=self.user,
            status=GoodsReceipt.STATUS_CONFIRMED,
            location=self.location,
        )
        entry_movement = StockMovement.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            product=self.product,
            location=self.location,
            operator=self.user,
            movement_type=StockMovement.TYPE_PURCHASE_ENTRY,
            quantity=Decimal("20.00"),
            stock_unit="UN",
            unit_cost=Decimal("2.00"),
            total_cost=Decimal("40.00"),
            nfe=invoice,
            nfe_item=item,
            receipt=receipt,
        )

        res = apply_cancellation(
            invoice=invoice,
            protocol="133260000012345",
            reason="Cancelamento posterior",
        )

        invoice.refresh_from_db()
        receipt.refresh_from_db()

        self.assertEqual(invoice.fiscal_status, InboundNFe.FISCAL_CANCELLED)
        self.assertEqual(invoice.status, InboundNFe.STATUS_CANCELLED)
        self.assertEqual(receipt.status, GoodsReceipt.STATUS_CANCELLED)
        self.assertEqual(res["reversals_created"], 1)

        # Verificar se o movimento de reversão foi criado
        reversal = StockMovement.all_objects.filter(
            reversal_of=entry_movement,
            movement_type=StockMovement.TYPE_NFE_CANCELLATION_REVERSAL,
        ).first()
        self.assertIsNotNone(reversal)
        self.assertEqual(reversal.quantity, Decimal("-20.00"))
        self.assertEqual(reversal.total_cost, Decimal("-40.00"))

        # Saldo líquido em estoque deve ser zero
        balance = StockMovement.all_objects.filter(product=self.product).aggregate(
            s=Decimal("0") + models_sum("quantity")
        )["s"]
        self.assertEqual(balance, Decimal("0.00"))

        # Idempotência: chamar novamente não duplica reversões
        res2 = apply_cancellation(invoice=invoice)
        self.assertEqual(res2["reversals_created"], 0)
        self.assertEqual(StockMovement.all_objects.filter(reversal_of=entry_movement).count(), 1)

    def test_cancellation_with_prior_consumption_creates_issue(self):
        """Se o estoque foi consumido antes do cancelamento, cria NFeIssue."""
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="33260800074569004784550100020957561914829153",
            number="2095756",
            series="1",
            status=InboundNFe.STATUS_RECEIVED,
            fiscal_status=InboundNFe.FISCAL_AUTHORIZED,
        )
        item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            invoice=invoice,
            item_number=1,
            description="Água Mineral",
            commercial_quantity=Decimal("10.00"),
            commercial_unit_value=Decimal("2.00"),
            product_total=Decimal("20.00"),
            product=self.product,
        )
        # Criado pelo efeito colateral: este teste exercita o cancelamento em
        # cima do movimento, sem afirmar sobre o objeto devolvido.
        StockMovement.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            product=self.product,
            location=self.location,
            operator=self.user,
            movement_type=StockMovement.TYPE_PURCHASE_ENTRY,
            quantity=Decimal("10.00"),
            stock_unit="UN",
            unit_cost=Decimal("2.00"),
            total_cost=Decimal("20.00"),
            nfe=invoice,
            nfe_item=item,
        )
        # Houve uma venda que consumiu 8 unidades
        StockMovement.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            product=self.product,
            location=self.location,
            operator=self.user,
            movement_type=StockMovement.TYPE_SALE_OUTPUT,
            quantity=Decimal("-8.00"),
            stock_unit="UN",
            unit_cost=Decimal("2.00"),
            total_cost=Decimal("-16.00"),
        )
        # Saldo agora é apenas 2, mas a nota que entrou foi de 10

        res = apply_cancellation(invoice=invoice, protocol="9999")
        self.assertGreaterEqual(res["issues_created"], 1)

        issue = NFeIssue.all_objects.filter(
            nfe=invoice,
            issue_type=NFeIssue.TYPE_CANCELLED_AFTER_STOCK_MOVEMENT,
        ).first()
        self.assertIsNotNone(issue)
        self.assertIn("saldo atual é de apenas 2", issue.description)

    def test_cancellation_flags_asset_and_creates_issue(self):
        """Se a NF-e cadastrou patrimônio, marca source_nfe_cancelled=True e cria NFeIssue."""
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="33260800074569004784550100020957561914829153",
            number="2095756",
            series="1",
            status=InboundNFe.STATUS_RECEIVED,
            fiscal_status=InboundNFe.FISCAL_AUTHORIZED,
        )
        item = InboundNFeItem.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            invoice=invoice,
            item_number=1,
            description="Geladeira Comercial",
            commercial_quantity=Decimal("1.00"),
            commercial_unit_value=Decimal("3500.00"),
            product_total=Decimal("3500.00"),
            product=self.asset_product,
        )
        asset = Asset.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            location=self.location,
            product=self.asset_product,
            nfe=invoice,
            nfe_item=item,
            purchase_price=Decimal("3500.00"),
            status=Asset.STATUS_IN_USE,
        )

        res = apply_cancellation(invoice=invoice, protocol="PROT-ASSET-CANCEL")
        asset.refresh_from_db()

        self.assertTrue(asset.source_nfe_cancelled)
        self.assertIn("foi cancelada na SEFAZ", asset.notes)
        self.assertEqual(res["assets_flagged"], 1)

        issue = NFeIssue.all_objects.filter(
            nfe=invoice,
            issue_type=NFeIssue.TYPE_CANCELLED_AFTER_RECEIPT,
        ).first()
        self.assertIsNotNone(issue)
        self.assertIn("Geladeira Comercial", issue.description)

    def test_parse_and_apply_cons_sit_cancelled(self):
        """Valida que o retorno retConsSitNFe com cStat 101 cancela a nota."""
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="33260800074569004784550100020957561914829153",
            number="2095756",
            series="1",
            status=InboundNFe.STATUS_PENDING_MAPPING,
            fiscal_status=InboundNFe.FISCAL_AUTHORIZED,
        )
        xml_response = """<?xml version="1.0" encoding="utf-8"?>
        <soap:Envelope xmlns:soap="http://www.w3.org/2003/05/soap-envelope">
          <soap:Body>
            <retConsSitNFe versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
              <tpAmb>1</tpAmb>
              <cStat>101</cStat>
              <xMotivo>Cancelamento de NF-e homologado</xMotivo>
              <chNFe>33260800074569004784550100020957561914829153</chNFe>
              <dhRecbto>2026-08-31T18:00:00-03:00</dhRecbto>
              <nProt>133260999999999</nProt>
            </retConsSitNFe>
          </soap:Body>
        </soap:Envelope>"""

        res = parse_and_apply_cons_sit_response(invoice, xml_response)
        self.assertTrue(res["is_cancelled"])
        self.assertEqual(res["cstat"], "101")
        invoice.refresh_from_db()
        self.assertEqual(invoice.fiscal_status, InboundNFe.FISCAL_CANCELLED)
        self.assertEqual(invoice.cancellation_protocol, "133260999999999")


def models_sum(field_name):
    from django.db.models import Sum
    return Sum(field_name)
