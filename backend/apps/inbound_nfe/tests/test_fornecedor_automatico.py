"""Fornecedor cadastrado sozinho na importação da nota de entrada.

Procura pelo CNPJ/CPF do emitente; se não existir, cria com razão social,
nome fantasia, IE, telefone e endereço da nota. Se já existir, só preenche o
que estiver vazio — o que alguém digitou no cadastro não é sobrescrito.
"""
from django.test import TestCase

from apps.accounts.models import Account
from apps.inbound_nfe.services.importer import process_uploaded_xml
from apps.restaurants.models import Restaurant
from apps.stock.models import Supplier

XML = """<?xml version="1.0" encoding="UTF-8"?>
<nfeProc versao="4.00" xmlns="http://www.portalfiscal.inf.br/nfe">
  <NFe><infNFe versao="4.00" Id="NFe33260808969770000159550010054463751287194822">
    <ide><nNF>5446375</nNF><serie>1</serie><dhEmi>2026-08-26T03:37:39-03:00</dhEmi></ide>
    <emit>
      <CNPJ>08969770000159</CNPJ>
      <xNome>RIO QUALITY COMERCIO DE ALIMENTOS S/A</xNome>
      <xFant>RIO QUALITY</xFant>
      <enderEmit>
        <xLgr>AV BRASIL</xLgr><nro>1000</nro><xBairro>PENHA</xBairro>
        <xMun>RIO DE JANEIRO</xMun><UF>RJ</UF><CEP>21012000</CEP><fone>2133334444</fone>
      </enderEmit>
      <IE>86123456</IE>
    </emit>
    <det nItem="1"><prod><cProd>1</cProd><cEAN>SEM GTIN</cEAN><xProd>ARROZ 5KG</xProd>
      <NCM>10063021</NCM><CFOP>5102</CFOP><uCom>UN</uCom><qCom>1</qCom><vUnCom>20</vUnCom>
      <vProd>20</vProd></prod></det>
    <total><ICMSTot><vProd>20</vProd><vNF>20</vNF></ICMSTot></total>
  </infNFe></NFe>
</nfeProc>"""


class FornecedorAutomaticoTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(name="Conta Forn", slug="conta-forn")
        self.restaurant = Restaurant.all_objects.create(account=self.account, trade_name="Loja")

    def _importar(self):
        return process_uploaded_xml(XML, account=self.account, restaurant=self.restaurant)

    def test_cria_o_fornecedor_com_os_dados_da_nota(self):
        self._importar()

        fornecedor = Supplier.all_objects.get(account=self.account, tax_id="08969770000159")
        self.assertEqual(fornecedor.name, "RIO QUALITY")
        self.assertEqual(fornecedor.legal_name, "RIO QUALITY COMERCIO DE ALIMENTOS S/A")
        self.assertEqual(fornecedor.state_registration, "86123456")
        self.assertEqual(fornecedor.street, "AV BRASIL")
        self.assertEqual(fornecedor.number, "1000")
        self.assertEqual(fornecedor.city, "RIO DE JANEIRO")
        self.assertEqual(fornecedor.state, "RJ")
        self.assertEqual(fornecedor.zip_code, "21012000")
        self.assertEqual(fornecedor.phone, "2133334444")

    def test_importar_de_novo_nao_duplica(self):
        self._importar()
        self._importar()

        self.assertEqual(Supplier.all_objects.filter(account=self.account).count(), 1)

    def test_fornecedor_existente_pelo_cnpj_formatado_so_ganha_o_que_falta(self):
        existente = Supplier.all_objects.create(
            account=self.account, name="Rio Quality (meu nome)",
            tax_id="08.969.770/0001-59", phone="21999990000",
        )

        self._importar()

        existente.refresh_from_db()
        self.assertEqual(Supplier.all_objects.filter(account=self.account).count(), 1)
        self.assertEqual(existente.name, "Rio Quality (meu nome)")
        self.assertEqual(existente.phone, "21999990000")
        self.assertEqual(existente.city, "RIO DE JANEIRO")

    def test_nome_ja_usado_por_outro_fornecedor_nao_derruba_a_importacao(self):
        """O nome é único na conta; o novo ganha o CNPJ no nome."""
        Supplier.all_objects.create(account=self.account, name="RIO QUALITY", tax_id="11111111000111")

        self._importar()

        novo = Supplier.all_objects.get(account=self.account, tax_id="08969770000159")
        self.assertIn("08969770000159", novo.name)
