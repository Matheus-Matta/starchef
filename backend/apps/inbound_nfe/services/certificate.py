import os
import tempfile
from django.conf import settings
from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.hazmat.primitives import serialization

# Exemplo de serviço abstrato para carregar certificados.
# Em produção, a senha pode vir de um Secret Manager ou variável segura.

def get_pfx_bytes_and_password(account, restaurant_id=None) -> tuple[bytes, bytes]:
    """Retorna os bytes do arquivo PFX e a senha em bytes."""
    from apps.invoices.models import FiscalConfig

    qs = FiscalConfig.all_objects.filter(account=account)
    if restaurant_id:
        config = qs.filter(restaurant_id=restaurant_id).first()
    else:
        config = qs.filter(certificate_file__isnull=False).first() or qs.first()

    if not config or (not config.certificate_file and not config.certificate_ref):
        raise ValueError("Certificado Digital A1 (.pfx) não configurado para esta unidade.")

    password = config.certificate_password or os.environ.get("CERT_PASSWORD", "")
    if not password:
        raise ValueError("Senha do certificado digital não informada no perfil fiscal.")

    pwd_bytes = password.encode() if isinstance(password, str) else password

    if config.certificate_file:
        try:
            if hasattr(config.certificate_file, 'path') and os.path.exists(config.certificate_file.path):
                with open(config.certificate_file.path, "rb") as f:
                    pfx_data = f.read()
            else:
                config.certificate_file.open("rb")
                pfx_data = config.certificate_file.read()
        except Exception:
            config.certificate_file.seek(0)
            pfx_data = config.certificate_file.read()
    else:
        with open(config.certificate_ref, "rb") as f:
            pfx_data = f.read()

    return pfx_data, pwd_bytes


def get_certificate_objects(account, restaurant_id=None):
    """
    Retorna (private_key, certificate, additional_certificates) em memória
    para uso em assinatura digital de XML.
    """
    pfx_data, pwd_bytes = get_pfx_bytes_and_password(account, restaurant_id=restaurant_id)
    return load_key_and_certificates(pfx_data, pwd_bytes)


def get_certificate_paths(account, restaurant_id=None) -> tuple[str, str]:
    """
    Retorna (caminho_cert_pem, caminho_key_pem) para usar em chamadas requests com mTLS.
    Atenção: Os arquivos gerados são temporários.

    Lê o certificado A1 (arquivo .pfx ou caminho) e senha do FiscalConfig.
    """
    pfx_data, password = get_pfx_bytes_and_password(account, restaurant_id=restaurant_id)

    private_key, certificate, additional_certificates = load_key_and_certificates(
        pfx_data,
        password
    )

    if not private_key or not certificate:
        raise ValueError("Falha ao ler chave privada ou certificado do arquivo PFX.")

    # Gerar o arquivo do certificado
    cert_fd, cert_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(cert_fd, "wb") as f:
        f.write(certificate.public_bytes(serialization.Encoding.PEM))
        if additional_certificates:
            for add_cert in additional_certificates:
                f.write(add_cert.public_bytes(serialization.Encoding.PEM))

    # Gerar o arquivo da chave
    key_fd, key_path = tempfile.mkstemp(suffix=".pem")
    with os.fdopen(key_fd, "wb") as f:
        f.write(
            private_key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption()
            )
        )

    return cert_path, key_path

def cleanup_temp_files(*paths):
    """
    Remove arquivos temporários gerados.
    """
    for p in paths:
        if p and os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
