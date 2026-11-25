"""Leitura e conferência do XML da NFC-e do desktop (`nota_do_desktop.py`)."""
import re
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.dateparse import parse_datetime

from apps.invoices.models import FiscalConfig, Invoice

LIMITE_DO_XML = 500_000
NS = "{http://www.portalfiscal.inf.br/nfe}"
_AUTORIZADA = {"100", "150"}


def ler(xml):
    if not isinstance(xml, str) or not xml.strip():
        raise ValidationError("Envie o XML da nota.")
    if len(xml) > LIMITE_DO_XML:
        raise ValidationError("XML grande demais para uma NFC-e.")
    # NF-e não usa DTD: entidade aqui só serve para ataque (billion laughs).
    if re.search(r"<!(DOCTYPE|ENTITY)", xml, re.I):
        raise ValidationError("XML com DTD não é aceito.")
    try:
        raiz = ET.fromstring(xml.strip().encode("utf-8"))
    except (ET.ParseError, ValueError) as exc:
        raise ValidationError("XML ilegível.") from exc
    inf = next(raiz.iter(f"{NS}infNFe"), None)
    if inf is None or next(raiz.iter("{http://www.w3.org/2000/09/xmldsig#}SignatureValue"), None) is None:
        raise ValidationError("O XML não é uma NFC-e assinada.")
    texto = leitor(inf)
    chave = (inf.get("Id") or "").removeprefix("NFe")
    if not re.fullmatch(r"[0-9A-Z]{44}", chave) or _dv(chave[:43]) != chave[43]:
        raise ValidationError("Chave de acesso inválida.")
    ide = {campo: texto(f"ide/{campo}") for campo in ("mod", "serie", "nNF", "tpEmis", "tpAmb", "cNF", "dhEmi")}
    cnpj = texto("emit/CNPJ")
    # A chave é feita desses campos: conferir um contra o outro pega XML editado.
    esperado = f"{cnpj}{ide['mod']:0>2}{ide['serie']:0>3}{ide['nNF']:0>9}{ide['tpEmis']}{ide['cNF']:0>8}"
    if ide["mod"] != FiscalConfig.MODEL_NFCE or chave[6:43] != esperado:
        raise ValidationError("A chave de acesso não corresponde aos dados da NFC-e.")
    protocolo, autorizada_em = _protocolo(raiz, chave)
    if not protocolo and ide["tpEmis"] != Invoice.EMISSION_CONTINGENCY:
        raise ValidationError("A nota ainda não foi autorizada pela SEFAZ.")
    return {
        **ide, "xml": xml, "chave": chave, "cnpj": cnpj, "protocolo": protocolo, "autorizada_em": autorizada_em,
        "texto": texto, "itens": inf.findall(f"{NS}det"), "crt": texto("emit/CRT"),
        "total": decimal(texto("total/ICMSTot/vNF")),
        "qr": next((e.text or "" for e in raiz.iter(f"{NS}qrCode")), "").strip(),
        "url": next((e.text or "" for e in raiz.iter(f"{NS}urlChave")), "").strip(),
        "digest": next((e.text or "" for e in raiz.iter("{http://www.w3.org/2000/09/xmldsig#}DigestValue")), ""),
    }


def _protocolo(raiz, chave):
    prot = next(raiz.iter(f"{NS}infProt"), None)
    if prot is None:
        return "", None
    texto = leitor(prot)
    if texto("chNFe") != chave or texto("cStat") not in _AUTORIZADA or not texto("nProt"):
        raise ValidationError("O protocolo do XML não autoriza esta nota.")
    return texto("nProt"), parse_datetime(texto("dhRecbto"))


def leitor(elemento):
    def texto(caminho):
        achado = None if elemento is None else elemento.find("/".join(NS + parte for parte in caminho.split("/")))
        return "" if achado is None else (achado.text or "").strip()

    return texto


def decimal(valor, casas="0.01"):
    try:
        return Decimal(valor or "0").quantize(Decimal(casas))
    except InvalidOperation as exc:
        raise ValidationError("Valor inválido no XML.") from exc


def _dv(corpo):
    """Módulo 11 da chave; letra do CNPJ alfanumérico vale ASCII − 48."""
    resto = sum((ord(c) - 48) * (2 + i % 8) for i, c in enumerate(reversed(corpo))) % 11
    return "0" if resto < 2 else str(11 - resto)
