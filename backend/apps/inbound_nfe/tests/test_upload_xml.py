from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model
from apps.accounts.models import Account
from apps.restaurants.models import Restaurant
from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, DFeDistributionDocument
from apps.inbound_nfe.views import InboundNFeViewSet

User = get_user_model()


class UploadXMLTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(name="Test Account")
        self.restaurant = Restaurant.all_objects.create(account=self.account, trade_name="Test Restaurant")
        self.user = User.objects.create_superuser(
            username="admin_upload",
            email="admin_upload@starchef.app",
            password="adminpassword123",
        )
        self.factory = APIRequestFactory()

    def test_upload_single_xml(self):
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe xmlns="http://www.portalfiscal.inf.br/nfe">
    <infNFe versao="4.00" Id="NFe33260808969770000159550010054463751287194822">
      <ide>
        <nNF>5446375</nNF>
        <serie>1</serie>
        <dhEmi>2026-08-26T03:37:39-03:00</dhEmi>
      </ide>
      <emit>
        <CNPJ>08969770000159</CNPJ>
        <xNome>RIO QUALITY COMERCIO DE ALIMENTOS S/A</xNome>
      </emit>
      <total>
        <ICMSTot>
          <vProd>135.60</vProd>
          <vNF>135.60</vNF>
        </ICMSTot>
      </total>
      <det nItem="1">
        <prod>
          <cProd>54286</cProd>
          <cEAN>17896508200031</cEAN>
          <xProd>ACUCAR REF. 1KG ALTO ALEGRE</xProd>
          <NCM>17019900</NCM>
          <CFOP>5102</CFOP>
          <uCom>FD10</uCom>
          <qCom>4.0000</qCom>
          <vUnCom>33.90</vUnCom>
          <vProd>135.60</vProd>
          <cEANTrib>17896508200031</cEANTrib>
          <uTrib>FD10</uTrib>
          <qTrib>4.0000</qTrib>
          <vUnTrib>33.90</vUnTrib>
        </prod>
        <imposto>
          <ICMS>
            <ICMS00>
              <orig>0</orig>
              <CST>00</CST>
              <modBC>3</modBC>
              <vBC>135.60</vBC>
              <pICMS>18.00</pICMS>
              <vICMS>24.40</vICMS>
            </ICMS00>
          </ICMS>
        </imposto>
      </det>
    </infNFe>
  </NFe>
</nfeProc>"""
        file = SimpleUploadedFile("nfe_teste.xml", xml_content.encode("utf-8"), content_type="text/xml")
        
        request = self.factory.post("/api/v1/inbound-nfe/upload-xml/", {"files": file}, format="multipart")
        force_authenticate(request, user=self.user)
        request.account = self.account

        view = InboundNFeViewSet.as_view({"post": "upload_xml"})
        response = view(request)
        print("DEBUG RESPONSE DATA:", response.data)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"]["total_processed"], 1)
        
        # Verificar banco
        invoice = InboundNFe.all_objects.filter(access_key="33260808969770000159550010054463751287194822").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.number, "5446375")
        self.assertEqual(invoice.supplier_name, "RIO QUALITY COMERCIO DE ALIMENTOS S/A")
        self.assertEqual(InboundNFeItem.all_objects.filter(invoice=invoice).count(), 1)
