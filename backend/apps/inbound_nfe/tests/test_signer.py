import datetime
import unittest
import xml.etree.ElementTree as ET
from apps.inbound_nfe.services.signer import sign_xml_node, validate_no_forbidden_prefixes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import hashes
from cryptography import x509
from cryptography.x509.oid import NameOID


class SignerTestCase(unittest.TestCase):
    def test_sign_xml_node(self):
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

        xml_text = (
            '<envEvento xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">'
            '<idLote>1</idLote>'
            '<evento versao="1.00">'
            '<infEvento Id="ID2102103526081234567800019055001000056021100056021301">'
            '<cOrgao>91</cOrgao>'
            '<tpAmb>2</tpAmb>'
            '<CNPJ>12345678000190</CNPJ>'
            '<chNFe>35260812345678000190550010000560211000560213</chNFe>'
            '<dhEvento>2026-09-01T14:00:00-03:00</dhEvento>'
            '<tpEvento>210210</tpEvento>'
            '<nSeqEvento>1</nSeqEvento>'
            '<verEvento>1.00</verEvento>'
            '<detEvento versao="1.00">'
            '<descEvento>Ciencia da Operacao</descEvento>'
            '</detEvento>'
            '</infEvento>'
            '</evento>'
            '</envEvento>'
        )

        signed = sign_xml_node(
            xml_text,
            'infEvento',
            'ID2102103526081234567800019055001000056021100056021301',
            key,
            cert
        )

        validate_no_forbidden_prefixes(signed)
        self.assertIn('Signature', signed)
        self.assertIn('SignatureValue', signed)
        self.assertIn('X509Certificate', signed)
        self.assertIn('SignedInfo', signed)
        self.assertNotIn('ds:Signature', signed)
        self.assertNotIn('ns0:', signed)
        self.assertNotIn('nfe:', signed)

    def test_science_signature_is_valid(self):
        """
        Teste obrigatório de conformidade com a SEFAZ:
        1. Gerar evento 210210
        2. Conferir infEvento/@Id correto
        3. Conferir Reference/@URI == '#' + infEvento/@Id
        4. Conferir SignatureMethod RSA-SHA1
        5. Conferir DigestMethod SHA-1
        6. Conferir Transforms: enveloped-signature e C14N 1.0
        7. Verificar assinatura criptograficamente
        8. Serializar
        9. Parsear novamente
        10. Verificar novamente a assinatura
        """
        from apps.inbound_nfe.services.signer import verify_xml_signature, validate_key_and_certificate
        from apps.inbound_nfe.services.manifestation import build_event_xml

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Test Dest')])
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

        # Validação do par de chaves
        validate_key_and_certificate(key, cert)

        access_key = "33260900074569004784550100020983901861776260"
        cnpj = "20078285000190"
        xml_str, ref_id = build_event_xml(
            cnpj=cnpj,
            access_key=access_key,
            event_type="science",
            seq=1,
        )

        # 2. Conferir Id
        expected_id = f"ID210210{access_key}01"
        self.assertEqual(ref_id, expected_id)

        signed_xml_str = sign_xml_node(
            xml_str,
            target_node_tag='infEvento',
            reference_id=ref_id,
            private_key=key,
            certificate=cert,
        )

        # 8 & 9. Parsear novamente
        parsed_doc = ET.fromstring(signed_xml_str)
        namespaces = {
            'nfe': 'http://www.portalfiscal.inf.br/nfe',
            'ds': 'http://www.w3.org/2000/09/xmldsig#',
        }

        # 3. Reference/@URI
        ref_el = parsed_doc.find('.//ds:Reference', namespaces)
        self.assertIsNotNone(ref_el)
        self.assertEqual(ref_el.get("URI"), f"#{expected_id}")

        # 4. SignatureMethod
        sig_method_el = parsed_doc.find('.//ds:SignatureMethod', namespaces)
        self.assertIsNotNone(sig_method_el)
        self.assertEqual(sig_method_el.get("Algorithm"), "http://www.w3.org/2000/09/xmldsig#rsa-sha1")

        # 5. DigestMethod
        digest_method_el = parsed_doc.find('.//ds:DigestMethod', namespaces)
        self.assertIsNotNone(digest_method_el)
        self.assertEqual(digest_method_el.get("Algorithm"), "http://www.w3.org/2000/09/xmldsig#sha1")

        # 6. Transforms
        transforms = parsed_doc.findall('.//ds:Transform', namespaces)
        self.assertEqual(len(transforms), 2)
        self.assertEqual(transforms[0].get("Algorithm"), "http://www.w3.org/2000/09/xmldsig#enveloped-signature")
        self.assertEqual(transforms[1].get("Algorithm"), "http://www.w3.org/TR/2001/REC-xml-c14n-20010315")

        # 7 & 10. Verificar assinatura criptograficamente no XML final
        self.assertTrue(verify_xml_signature(signed_xml_str))
