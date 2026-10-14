"""Um A1 de verdade (PKCS#12) para os testes da ACBrLib.

O provedor confere o certificado antes de chamar o comunicador
(`acbrlib/certificado.py`), então um base64 qualquer não passa mais.
"""
import base64
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization.pkcs12 import serialize_key_and_certificates
from cryptography.x509.oid import NameOID

CNPJ = "11222333000181"
SENHA = "s3nh4-secreta"
AGORA = datetime.datetime(2026, 10, 13, 12, tzinfo=datetime.timezone.utc)


def pfx(*, cnpj=CNPJ, senha=SENHA, vence=None):
    vence = vence or datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=200)
    chave = rsa.generate_private_key(public_exponent=65537, key_size=1024)
    nome = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, f"RESTAURANTE TESTE LTDA:{cnpj}")])
    cert = (
        x509.CertificateBuilder().subject_name(nome).issuer_name(nome)
        .public_key(chave.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(vence - datetime.timedelta(days=400)).not_valid_after(vence)
        .sign(chave, hashes.SHA256())
    )
    conteudo = serialize_key_and_certificates(
        b"a1", chave, cert, None, serialization.BestAvailableEncryption(senha.encode()))
    return base64.b64encode(conteudo).decode()
