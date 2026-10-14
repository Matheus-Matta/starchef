"""O certificado A1 conferido aqui, antes do comunicador — com o motivo pelo nome.

A ACBrLib recusa com a frase técnica dela, a mesma para senha errada, arquivo
vencido e certificado de outra empresa; o operador não sabia o que trocar.
Aqui cada caso vira um `motivo` (`certificado_ausente`, `senha_invalida`,
`certificado_invalido`, `certificado_vencido`, `cnpj_diferente`) e uma frase
que diz a providência.

NADA DO SEGREDO SAI DAQUI: nem o arquivo, nem o base64, nem a senha vão para a
mensagem (que fica gravada na nota) ou para o log. A exceção da criptografia
também não sobe na cadeia (`from None`): o texto dela é técnico e não ajuda.
"""
import base64
import binascii
import datetime
import hashlib
import logging
import re

from cryptography.hazmat.primitives.serialization.pkcs12 import load_key_and_certificates
from cryptography.x509.oid import NameOID

from apps.invoices.providers_erros import FiscalConfigurationError

logger = logging.getLogger(__name__)


class CertificadoRecusado(FiscalConfigurationError):
    """O A1 não serve para emitir; `motivo` diz por quê."""

    def __init__(self, motivo, mensagem):
        super().__init__(f"Certificado A1: {mensagem}")
        self.motivo = motivo


def conferir_certificado(pfx_base64, senha, *, cnpj_emitente, agora=None):
    """Levanta `CertificadoRecusado` se o A1 não puder assinar por este CNPJ."""
    if not (pfx_base64 or "").strip():
        raise CertificadoRecusado(
            "certificado_ausente",
            "a empresa não tem certificado cadastrado (ou o arquivo não está neste "
            "servidor). Envie o .pfx na configuração fiscal.",
        )
    chave = _impressao(pfx_base64, senha or "")
    if chave not in _LIDOS:
        if len(_LIDOS) >= 32:
            _LIDOS.clear()
        _LIDOS[chave] = _ler(pfx_base64, senha or "")
    if _LIDOS[chave] is None:
        return  # formato que a biblioteca não lê: a ACBrLib decide (ver `_ler`)
    vence_em, cnpj = _LIDOS[chave]
    agora = agora or datetime.datetime.now(datetime.timezone.utc)
    if vence_em <= agora:
        raise CertificadoRecusado(
            "certificado_vencido",
            f"venceu em {vence_em:%d/%m/%Y}. Renove com a certificadora e envie o novo .pfx.",
        )
    emitente = re.sub(r"\D", "", cnpj_emitente or "")
    # A RAIZ (8 primeiros dígitos): o A1 da matriz assina a nota da filial.
    if cnpj and emitente and cnpj[:8] != emitente[:8]:
        raise CertificadoRecusado(
            "cnpj_diferente",
            f"é do CNPJ {_formatar(cnpj)}, e a nota é do {_formatar(emitente)}. "
            "Envie o certificado desta empresa.",
        )


#: (validade, CNPJ) por certificado: abrir o PKCS#12 custa, e é a cada nota.
#: A chave é um HASH — o segredo não fica guardado em memória à toa.
_LIDOS = {}


def _impressao(pfx_base64, senha):
    return hashlib.sha256(f"{senha}\0{pfx_base64}".encode()).hexdigest()


def _ler(pfx_base64, senha):
    """(validade, CNPJ) do A1, `CertificadoRecusado` dizendo por quê, ou
    `None` quando a biblioteca não lê o formato (não é motivo de recusa)."""
    try:
        conteudo = base64.b64decode(pfx_base64, validate=False)
    except (binascii.Error, ValueError):
        raise CertificadoRecusado(
            "certificado_invalido", "o arquivo cadastrado não é um .pfx válido."
        ) from None
    try:
        _chave_privada, cert, _ = load_key_and_certificates(conteudo, senha.encode())
    except ValueError as erro:
        texto = str(erro).lower()
        if any(p in texto for p in ("password", "mac", "decrypt", "verify")):
            raise CertificadoRecusado(
                "senha_invalida",
                "a senha cadastrada não abre o certificado. Confira a senha na "
                "configuração fiscal.",
            ) from None
        raise CertificadoRecusado(
            "certificado_invalido",
            "o arquivo cadastrado não é um .pfx válido (corrompido ou de outro formato).",
        ) from None
    except Exception as erro:  # noqa: BLE001 — ver abaixo
        # A1 em criptografia antiga (RC2/3DES) é comum, e a ACBrLib o lê; a
        # `cryptography` levanta `UnsupportedAlgorithm` para ele. Esta
        # conferência é só ajuda: travar aqui virava "erro interno" no
        # cancelamento e na emissão de um certificado que funciona.
        logger.warning("Certificado A1 não conferido no backend (%s); segue para a ACBrLib.",
                       type(erro).__name__)
        return None
    if cert is None:
        raise CertificadoRecusado("certificado_invalido", "o .pfx não contém certificado.")
    nome = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
    achado = re.search(r"(\d{14})", nome[0].value if nome else "")
    return cert.not_valid_after_utc, achado.group(1) if achado else ""


def _formatar(cnpj):
    return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"
