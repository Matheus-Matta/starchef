import unittest
from unittest.mock import patch, MagicMock
from apps.inbound_nfe.services.manifestation import (
    build_event_xml,
    build_soap_envelope,
    parse_event_response,
    manifest_nfe,
    register_science,
    fetch_full_xml,
)
from apps.inbound_nfe.services.sefaz_client import NFeDistribuicaoClient, DFeDocument
from apps.inbound_nfe.models import InboundNFe, NFeManifestation, InboundNFeItem
from apps.accounts.models import Account
from apps.restaurants.models import Restaurant
from apps.invoices.models import FiscalConfig
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.x509.oid import NameOID
import datetime
import xml.etree.ElementTree as ET
from django.test import TestCase


class ManifestationTestCase(TestCase):
    def setUp(self):
        self.account = Account.objects.create(
            name="Conta Teste",
            slug="conta-teste",
            document="12345678000190",
        )
        self.restaurant = Restaurant.objects.create(
            account=self.account,
            trade_name="Restaurante Teste",
            legal_name="Restaurante Teste LTDA",
            cnpj="12345678000190",
        )
        self.fiscal_config = FiscalConfig.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            cnpj="12345678000190",
            certificate_password="fake-password",
            uf="RJ",
        )

    def test_build_event_xml(self):
        xml_str, ref_id = build_event_xml(
            cnpj="12345678000190",
            access_key="35260812345678000190550010000560211000560213",
            event_type="science",
            environment="production",
        )
        self.assertEqual(ref_id, "ID2102103526081234567800019055001000056021100056021301")
        self.assertIn("<tpEvento>210210</tpEvento>", xml_str)
        self.assertIn("<cOrgao>91</cOrgao>", xml_str)
        self.assertIn("<descEvento>Ciencia da Operacao</descEvento>", xml_str)
        # Garantir ausência de prefixos proibidos
        self.assertNotIn("ns0:", xml_str)
        self.assertNotIn("nfe:", xml_str)
        self.assertNotIn("ds:", xml_str)
        self.assertTrue(xml_str.startswith('<envEvento xmlns="http://www.portalfiscal.inf.br/nfe"'))

    def test_build_event_xml_not_performed_requires_reason(self):
        with self.assertRaises(ValueError):
            build_event_xml(
                cnpj="12345678000190",
                access_key="35260812345678000190550010000560211000560213",
                event_type="not_performed",
                reason="curto",
            )

    def test_parse_event_response_success(self):
        xml_response = (
            '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            '<soap12:Body>'
            '<nfeRecepcaoEventoResult xmlns="http://www.portalfiscal.inf.br/nfe/wsdl/NFeRecepcaoEvento4">'
            '<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">'
            '<cStat>128</cStat>'
            '<xMotivo>Lote de Evento Processado</xMotivo>'
            '<retEvento versao="1.00">'
            '<infEvento>'
            '<cStat>135</cStat>'
            '<xMotivo>Evento registrado e vinculado a NF-e</xMotivo>'
            '<nProt>135260000123456</nProt>'
            '<dhRegEvento>2026-09-01T14:30:00-03:00</dhRegEvento>'
            '</infEvento>'
            '</retEvento>'
            '</retEnvEvento>'
            '</nfeRecepcaoEventoResult>'
            '</soap12:Body>'
            '</soap12:Envelope>'
        )
        resp = parse_event_response(xml_response)
        self.assertEqual(resp.batch_cstat, "128")
        self.assertEqual(resp.event_cstat, "135")
        self.assertEqual(resp.protocol, "135260000123456")
        self.assertTrue(resp.is_success)

        # Valida desempacotamento como tupla (retrocompatibilidade)
        cstat, reason, dh = resp
        self.assertEqual(cstat, "135")
        self.assertIn("registrado e vinculado", reason)

    def test_build_cons_chnfe_request(self):
        client = NFeDistribuicaoClient(account=self.account, restaurant_id=self.restaurant.id)
        req_xml = client._build_cons_chnfe_request(
            uf_code="33",
            cnpj="12345678000190",
            access_key="35260812345678000190550010000560211000560213",
        )
        self.assertIn("<cUFAutor>33</cUFAutor>", req_xml)
        self.assertIn("<CNPJ>12345678000190</CNPJ>", req_xml)
        self.assertIn("<consChNFe>", req_xml)
        self.assertIn("<chNFe>35260812345678000190550010000560211000560213</chNFe>", req_xml)

    @patch("apps.inbound_nfe.services.manifestation.get_certificate_objects")
    @patch("apps.inbound_nfe.services.manifestation.get_certificate_paths")
    @patch("apps.inbound_nfe.services.manifestation.cleanup_temp_files")
    @patch("requests.post")
    def test_manifest_nfe_flow(
        self, mock_post, mock_cleanup, mock_get_paths, mock_get_objects
    ):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test')])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
            .sign(key, hashes.SHA256())
        )

        mock_get_objects.return_value = (key, cert, [])
        mock_get_paths.return_value = ("/tmp/cert.pem", "/tmp/key.pem")

        mock_resp = MagicMock()
        mock_resp.text = (
            '<soap12:Envelope xmlns:soap12="http://www.w3.org/2003/05/soap-envelope">'
            '<soap12:Body>'
            '<retEnvEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">'
            '<retEvento versao="1.00">'
            '<infEvento>'
            '<cStat>135</cStat>'
            '<xMotivo>Evento registrado e vinculado</xMotivo>'
            '<nProt>135260000999</nProt>'
            '</infEvento>'
            '</retEvento>'
            '</retEnvEvento>'
            '</soap12:Body>'
            '</soap12:Envelope>'
        )
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        resp = manifest_nfe(
            account=self.account,
            cnpj="12345678000190",
            access_key="35260812345678000190550010000560211000560213",
            event_type="science",
        )

        self.assertEqual(resp.event_cstat, "135")
        self.assertEqual(resp.protocol, "135260000999")
        self.assertTrue(mock_post.called)
        self.assertTrue(mock_cleanup.called)

    @patch("apps.inbound_nfe.services.manifestation.manifest_nfe")
    @patch("apps.inbound_nfe.services.manifestation.fetch_full_xml")
    def test_register_science_and_idempotency(self, mock_fetch_xml, mock_manifest):
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="35260812345678000190550010000560211000560213",
            status=InboundNFe.STATUS_SUMMARY,
            xml_status=InboundNFe.XML_STATUS_SUMMARY_ONLY,
            manifestation_status=InboundNFe.MANIFEST_NONE,
        )

        mock_manifest_resp = MagicMock()
        mock_manifest_resp.batch_cstat = "128"
        mock_manifest_resp.batch_reason = "Lote Processado"
        mock_manifest_resp.event_cstat = "135"
        mock_manifest_resp.event_reason = "Evento registrado e vinculado a NF-e"
        mock_manifest_resp.protocol = "135260000999"
        mock_manifest_resp.registered_at = datetime.datetime.now(datetime.timezone.utc)
        mock_manifest_resp.raw_xml = "<xml>ok</xml>"
        mock_manifest_resp.request_xml = "<req>env</req>"
        mock_manifest_resp.is_success = True
        mock_manifest.return_value = mock_manifest_resp
        mock_fetch_xml.return_value = True

        # 1ª Execução: deve transmitir evento e registrar ciência
        ok, msg = register_science(invoice)
        self.assertTrue(ok)
        self.assertIn("registrada", msg)
        self.assertEqual(mock_manifest.call_count, 1)

        manifestation = NFeManifestation.all_objects.filter(invoice=invoice).first()
        self.assertIsNotNone(manifestation)
        self.assertEqual(manifestation.status, NFeManifestation.STATUS_ACCEPTED)
        self.assertEqual(manifestation.protocol, "135260000999")

        # 2ª Execução: Idempotência! Não deve chamar manifest_nfe novamente
        mock_manifest.reset_mock()
        ok2, msg2 = register_science(invoice)
        self.assertTrue(ok2)
        self.assertIn("já registrada", msg2)
        self.assertEqual(mock_manifest.call_count, 0)

    @patch("apps.inbound_nfe.services.manifestation.manifest_nfe")
    @patch("apps.inbound_nfe.services.manifestation.fetch_full_xml")
    def test_register_science_retry_preserves_history_and_keeps_sequence_1(self, mock_fetch_xml, mock_manifest):
        invoice = InboundNFe.objects.create(
            account=self.account,
            restaurant=self.restaurant,
            access_key="35260899999999000190550010000560211000560219",
            status=InboundNFe.STATUS_SUMMARY,
            xml_status=InboundNFe.XML_STATUS_SUMMARY_ONLY,
            manifestation_status=InboundNFe.MANIFEST_NONE,
        )

        # Tentativa 1: Rejeição 404 (prefixo proibido ou validação formal)
        resp_404 = MagicMock()
        resp_404.batch_cstat = "404"
        resp_404.batch_reason = "Rejeicao: Uso de prefixo de namespace nao permitido"
        resp_404.event_cstat = None
        resp_404.event_reason = None
        resp_404.protocol = ""
        resp_404.registered_at = None
        resp_404.raw_xml = "<ret>404</ret>"
        resp_404.request_xml = "<req>env1</req>"
        resp_404.is_success = False

        mock_manifest.return_value = resp_404
        ok1, msg1 = register_science(invoice)
        self.assertFalse(ok1)
        self.assertIn("404", msg1)

        m = NFeManifestation.all_objects.filter(invoice=invoice, sequence=1).first()
        self.assertIsNotNone(m)
        self.assertEqual(m.status, NFeManifestation.STATUS_REJECTED)
        self.assertEqual(m.sequence, 1)

        # Tentativa 2: Sucesso após correção do XML (sem prefixos)
        resp_135 = MagicMock()
        resp_135.batch_cstat = "128"
        resp_135.batch_reason = "Lote Processado"
        resp_135.event_cstat = "135"
        resp_135.event_reason = "Evento registrado e vinculado a NF-e"
        resp_135.protocol = "135260000777"
        resp_135.registered_at = datetime.datetime.now(datetime.timezone.utc)
        resp_135.raw_xml = "<ret>135</ret>"
        resp_135.request_xml = "<req>env2</req>"
        resp_135.is_success = True

        mock_manifest.return_value = resp_135
        mock_fetch_xml.return_value = True

        ok2, msg2 = register_science(invoice)
        self.assertTrue(ok2)

        m.refresh_from_db()
        self.assertEqual(m.status, NFeManifestation.STATUS_ACCEPTED)
        self.assertEqual(m.sequence, 1)  # Permanece sequence 1 conforme regra SEFAZ
        self.assertEqual(m.protocol, "135260000777")
        self.assertEqual(len(m.history), 1)  # Tentativa 404 foi preservada no histórico
        self.assertEqual(m.history[0]["sefaz_batch_status"], "404")
