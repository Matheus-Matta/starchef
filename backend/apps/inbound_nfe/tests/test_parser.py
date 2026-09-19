import unittest
from decimal import Decimal
from pathlib import Path
from apps.inbound_nfe.services.xml_parser import (
    parse_nfe_xml,
    detect_document_type,
    DOC_RES_NFE,
    DOC_PROC_NFE,
    DOC_RES_EVENTO,
    DOC_PROC_EVENTO,
    DOC_UNKNOWN,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


class XMLParserTestCase(unittest.TestCase):
    def test_detect_document_type(self):
        self.assertEqual(detect_document_type("resNFe_v1.01.xsd"), DOC_RES_NFE)
        self.assertEqual(detect_document_type("procNFe_v4.00.xsd"), DOC_PROC_NFE)
        self.assertEqual(detect_document_type("resEvento_v1.01.xsd"), DOC_RES_EVENTO)
        self.assertEqual(detect_document_type("procEventoNFe_v1.00.xsd"), DOC_PROC_EVENTO)
        self.assertEqual(detect_document_type("unknown_schema.xsd"), DOC_UNKNOWN)

    def test_parse_res_nfe(self):
        xml_path = FIXTURES_DIR / "res_nfe.xml"
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        parsed = parse_nfe_xml(xml_content)

        self.assertEqual(parsed.access_key, "35260812345678000190550010000560211000560213")
        self.assertEqual(parsed.supplier_cnpj, "12345678000190")
        self.assertEqual(parsed.supplier_name, "ABC ALIMENTOS LTDA")
        self.assertEqual(parsed.total_invoice, Decimal('4382.00'))
        self.assertEqual(len(parsed.items), 0)

    def test_parse_nfe_proc(self):
        xml_path = FIXTURES_DIR / "nfe_proc.xml"
        with open(xml_path, 'r', encoding='utf-8') as f:
            xml_content = f.read()

        parsed = parse_nfe_xml(xml_content)

        self.assertEqual(parsed.access_key, "35260812345678000190550010000560211000560213")
        self.assertEqual(parsed.number, "56021")
        self.assertEqual(parsed.series, "1")
        self.assertEqual(parsed.supplier_cnpj, "12345678000190")
        self.assertEqual(parsed.supplier_name, "ABC ALIMENTOS LTDA")
        self.assertEqual(parsed.total_products, Decimal('300.00'))
        self.assertEqual(parsed.total_invoice, Decimal('305.00'))
        self.assertEqual(len(parsed.items), 1)

        item = parsed.items[0]
        self.assertEqual(item.item_number, 1)
        self.assertEqual(item.supplier_code, "12345")
        self.assertEqual(item.ean, "7891234567890")
        self.assertEqual(item.description, "ARROZ T1 FD 30KG")
        self.assertEqual(item.commercial_quantity, Decimal('2.0000'))
        self.assertEqual(item.commercial_unit_value, Decimal('150.00'))
        self.assertEqual(item.taxable_quantity, Decimal('60.0000'))
        self.assertEqual(item.product_total, Decimal('300.00'))
        self.assertEqual(item.freight, Decimal('10.00'))
        self.assertEqual(item.discount, Decimal('5.00'))
