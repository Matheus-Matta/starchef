import datetime
import os
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.exceptions import ValidationError
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import serialize_key_and_certificates
from cryptography.x509.oid import NameOID

from apps.accounts.models import Account
from apps.restaurants.models import Branch, Restaurant
from apps.invoices.models import FiscalConfig
from apps.invoices.serializers import FiscalConfigSerializer, parse_and_validate_certificate
from apps.inbound_nfe.services.certificate import get_certificate_paths, cleanup_temp_files


def generate_test_pfx(cn: str = "TESTE RESTAURANTE LTDA:12345678000195", password: str = "senha123", days_valid: int = 365) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.COUNTRY_NAME, "BR"),
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "StarChef Testes"),
        x509.NameAttribute(NameOID.COMMON_NAME, cn),
    ])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=days_valid))
        .sign(key, hashes.SHA256())
    )
    return serialize_key_and_certificates(
        b"cert",
        key,
        cert,
        None,
        serialization.BestAvailableEncryption(password.encode()) if password else serialization.NoEncryption()
    )


class CertificateValidationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.pfx_bytes = generate_test_pfx(
            cn="MEU RESTAURANTE LTDA:98765432000188",
            password="segredo_forte_123",
            days_valid=180
        )

    def test_parse_and_validate_certificate_success(self):
        valid_until, cn, cnpj = parse_and_validate_certificate(self.pfx_bytes, "segredo_forte_123")
        self.assertEqual(cn, "MEU RESTAURANTE LTDA:98765432000188")
        self.assertEqual(cnpj, "98765432000188")
        self.assertIsNotNone(valid_until)
        self.assertGreater(valid_until, datetime.datetime.now(datetime.timezone.utc))

    def test_parse_and_validate_certificate_wrong_password(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate_certificate(self.pfx_bytes, "senha_errada")
        self.assertIn("certificate_password", ctx.exception.detail)

    def test_parse_and_validate_certificate_corrupted_file(self):
        with self.assertRaises(ValidationError) as ctx:
            parse_and_validate_certificate(b"bytes_invalidos_nao_pfx", "qualquer_senha")
        self.assertIn("certificate_file", ctx.exception.detail)


class FiscalConfigCertificateIntegrationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.account = Account.objects.create(name="Conta Teste")
        cls.restaurant = Restaurant.objects.create(account=cls.account, trade_name="Restaurante Teste", cnpj="98765432000188")
        cls.branch = Branch.objects.create(account=cls.account, restaurant=cls.restaurant, name="Matriz")
        cls.pfx_bytes = generate_test_pfx(
            cn="RESTAURANTE INTEGRACAO LTDA:98765432000188",
            password="senha_fiscal_123"
        )

    def test_create_fiscal_config_with_certificate_file(self):
        from apps.core.tenant import tenant_context
        uploaded_file = SimpleUploadedFile(
            name="certificado_a1.pfx",
            content=self.pfx_bytes,
            content_type="application/x-pkcs12"
        )
        data = {
            "account": self.account.id,
            "restaurant": str(self.restaurant.id),
            "branch": str(self.branch.id),
            "cnpj": "98765432000188",
            "uf": "SP",
            "certificate_file": uploaded_file,
            "certificate_password": "senha_fiscal_123",
        }
        with tenant_context(self.account):
            serializer = FiscalConfigSerializer(data=data)
            self.assertTrue(serializer.is_valid(), serializer.errors)
            config = serializer.save(account=self.account)

            self.assertEqual(config.certificate_name, "RESTAURANTE INTEGRACAO LTDA:98765432000188")
            self.assertEqual(config.certificate_cnpj, "98765432000188")
            self.assertIsNotNone(config.certificate_valid_until)
            self.assertTrue(config.certificate_file)

            # GET representation não deve expor a senha
            rep = FiscalConfigSerializer(config).data
            self.assertNotIn("certificate_password", rep)
            self.assertTrue(rep["has_certificate"])
            self.assertTrue(rep["has_certificate_password"])
            self.assertEqual(rep["certificate_cnpj"], "98765432000188")

            # Testar extração de paths PEM para mTLS SEFAZ
            cert_path, key_path = get_certificate_paths(self.account)
            try:
                self.assertTrue(os.path.exists(cert_path))
                self.assertTrue(os.path.exists(key_path))
                with open(cert_path, "r") as f:
                    content = f.read()
                    self.assertIn("BEGIN CERTIFICATE", content)
                with open(key_path, "r") as f:
                    content = f.read()
                    self.assertIn("BEGIN RSA PRIVATE KEY", content)
            finally:
                cleanup_temp_files(cert_path, key_path)
                self.assertFalse(os.path.exists(cert_path))
                self.assertFalse(os.path.exists(key_path))
