"""
Utilitarios fiscais puros (sem estado): chave de acesso, QR Code NFC-e e tributos.

Implementam a parte *deterministica* da NFC-e/NF-e — o que nao depende de
certificado nem da SEFAZ. As partes que dependem de integracao externa
(assinatura A1, transmissao, protocolo de autorizacao) ficam nos providers,
propositalmente em branco ate a configuracao.

Referencias: Manual de Orientacao do Contribuinte (MOC) NF-e/NFC-e.
"""
import hashlib
import secrets
from decimal import ROUND_HALF_UP, Decimal

# Codigo IBGE da UF (cUF) — usado no inicio da chave de acesso.
UF_CODES = {
    "RO": "11", "AC": "12", "AM": "13", "RR": "14", "PA": "15", "AP": "16", "TO": "17",
    "MA": "21", "PI": "22", "CE": "23", "RN": "24", "PB": "25", "PE": "26", "AL": "27",
    "SE": "28", "BA": "29", "MG": "31", "ES": "32", "RJ": "33", "SP": "35",
    "PR": "41", "SC": "42", "RS": "43", "MS": "50", "MT": "51", "GO": "52", "DF": "53",
}

TWO = Decimal("0.01")


def only_digits(value):
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def dv_mod11(key43):
    """Digito verificador (cDV) da chave: modulo 11, pesos ciclicos de 2 a 9."""
    weights = [2, 3, 4, 5, 6, 7, 8, 9]
    total = sum(int(digit) * weights[i % 8] for i, digit in enumerate(reversed(key43)))
    remainder = total % 11
    dv = 11 - remainder
    return 0 if dv >= 10 else dv


def random_numeric_code(length=8):
    """cNF: codigo numerico aleatorio que compoe a chave (anti-fraude)."""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def build_access_key(*, uf, emission_date, cnpj, model, series, number, numeric_code=None, emission_type="1"):
    """Monta a chave de acesso de 44 digitos (43 + DV).

    Layout: cUF(2) AAMM(4) CNPJ(14) mod(2) serie(3) nNF(9) tpEmis(1) cNF(8) cDV(1).
    """
    cuf = UF_CODES.get((uf or "").upper(), "00")
    aamm = emission_date.strftime("%y%m")
    cnpj14 = only_digits(cnpj).rjust(14, "0")[:14]
    mod = str(model).rjust(2, "0")
    serie3 = str(series).rjust(3, "0")[-3:]
    nnf9 = str(number).rjust(9, "0")[-9:]
    cnf8 = (numeric_code or random_numeric_code()).rjust(8, "0")[-8:]

    key43 = f"{cuf}{aamm}{cnpj14}{mod}{serie3}{nnf9}{emission_type}{cnf8}"
    return f"{key43}{dv_mod11(key43)}", cnf8


def build_nfce_qrcode(*, access_key, environment, csc_id, csc_token, base_url, version="2"):
    """QR Code da NFC-e no modo ONLINE (versao 2.00).

    Formato: {base_url}?p=<chave>|<versao>|<tpAmb>|<idCSC>|<cHashQRCode>
    onde cHashQRCode = SHA1( chave|versao|tpAmb|idCSC|CSC ) em hex maiusculo.

    Enquanto o CSC/base_url nao forem configurados, o QR sai com os campos em
    branco — a estrutura ja fica correta e o hash passa a valer quando o CSC entrar.
    """
    params = f"{access_key}|{version}|{environment}|{csc_id or ''}"
    # SHA-1 é obrigatório no leiaute 2.00 do QR Code NFC-e. O parâmetro deixa
    # explícito que ele não está sendo usado como primitiva de segurança geral.
    digest = hashlib.sha1(
        f"{params}|{csc_token or ''}".encode(),
        usedforsecurity=False,
    ).hexdigest().upper()
    data = f"{params}|{digest}"
    qr_content = f"{base_url}?p={data}" if base_url else f"?p={data}"
    return qr_content


def format_access_key(access_key):
    """Agrupa a chave em blocos de 4 para exibicao no cupom."""
    key = only_digits(access_key)
    return " ".join(key[i:i + 4] for i in range(0, len(key), 4))


def compute_item_taxes(*, total_price, profile):
    """Calcula os valores de tributos de um item a partir do perfil fiscal.

    Para Simples Nacional os valores costumam ser zero (o imposto ja esta no DAS),
    entao os defaults do perfil sao 0 — configure as aliquotas quando necessario.
    Retorna um dict pronto para preencher o InvoiceItem.
    """
    base = Decimal(str(total_price or 0))

    def pct(rate):
        return (base * Decimal(str(rate or 0)) / Decimal("100")).quantize(TWO, rounding=ROUND_HALF_UP)

    icms_value = pct(profile.icms_rate if profile else 0)
    pis_value = pct(profile.pis_rate if profile else 0)
    cofins_value = pct(profile.cofins_rate if profile else 0)
    approx_value = pct(profile.approx_tax_rate if profile else 0)  # Lei 12.741 (tributos aprox.)
    return {
        "icms_base": base,
        "icms_rate": Decimal(str(profile.icms_rate if profile else 0)),
        "icms_value": icms_value,
        "pis_value": pis_value,
        "cofins_value": cofins_value,
        "approx_tax_value": approx_value,
    }
