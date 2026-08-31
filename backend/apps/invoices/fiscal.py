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


# ---------------------------------------------------------------- validacao
#
# Um item so vira NFC-e valida se o perfil fiscal do produto estiver completo.
# O que existia antes era o contrario disso: `_build_item` preenchia o que
# faltasse com `00000000`, `5102`, `102` e `49` na hora de transmitir — depois
# de o cliente ja ter pago, longe de quem podia corrigir, e sem deixar rastro.
#
# Os defaults nao sao todos iguais. NCM `00000000` e o mais perigoso porque
# pode ser ACEITO e gerar um documento fiscalmente errado, que e pior do que
# uma recusa. CFOP 5102 esta certo na esmagadora maioria da venda de balcao,
# mas erra em producao propria (5101) e substituicao tributaria (5405).
# PIS/COFINS 49 ("outras operacoes") e amplamente aceito e continua sendo um
# default legitimo. Por isso a validacao aponta o que falta em vez de recusar
# tudo: quem decide o rigor e `FiscalConfig.strict_fiscal_profile`.

SIMPLES_REGIMES = {"1", "2"}


def _issue(field, label, message, **extra):
    return {"field": field, "label": label, "message": message, **extra}


def icms_situation_field(crt):
    """Qual campo de situacao tributaria do ICMS vale para este regime.

    Simples Nacional usa CSOSN; regime normal usa CST. Trocar os dois nao e
    detalhe: um CSOSN numa empresa de regime normal e recusado pela SEFAZ.
    """
    return "csosn" if str(crt) in SIMPLES_REGIMES else "cst_icms"


def fiscal_profile_issues(profile, *, crt, subject=""):
    """Pendencias que impedem um perfil fiscal de virar item de NFC-e.

    Nunca levanta: alimenta tanto a conferencia de tela quanto a decisao de
    emitir, e um cadastro vazio demais precisa virar lista, nao excecao.
    """
    prefix = f"{subject}: " if subject else ""
    if profile is None:
        return [
            _issue(
                "fiscal_profile",
                "Perfil fiscal",
                f"{prefix}sem perfil fiscal definido.",
                subject=subject,
            )
        ]

    issues = []
    ncm = only_digits(getattr(profile, "ncm", ""))
    if not ncm:
        issues.append(_issue("ncm", "NCM", f"{prefix}NCM nao informado.", subject=subject))
    elif len(ncm) != 8:
        issues.append(
            _issue("ncm", "NCM", f"{prefix}NCM deve ter 8 digitos.", subject=subject)
        )

    cfop = only_digits(getattr(profile, "cfop", ""))
    if not cfop:
        issues.append(_issue("cfop", "CFOP", f"{prefix}CFOP nao informado.", subject=subject))
    elif len(cfop) != 4:
        issues.append(
            _issue("cfop", "CFOP", f"{prefix}CFOP deve ter 4 digitos.", subject=subject)
        )

    field = icms_situation_field(crt)
    if field == "csosn":
        if not getattr(profile, "csosn", ""):
            issues.append(
                _issue(
                    "csosn",
                    "CSOSN",
                    f"{prefix}CSOSN nao informado (empresa no Simples Nacional).",
                    subject=subject,
                )
            )
    elif not getattr(profile, "cst_icms", ""):
        issues.append(
            _issue(
                "cst_icms",
                "CST do ICMS",
                f"{prefix}CST do ICMS nao informado (empresa em regime normal).",
                subject=subject,
            )
        )
    return issues


def fiscal_item_issues(item, *, crt):
    """Mesma validacao, aplicada ao item ja congelado na nota.

    O item guarda a tributacao COPIADA do perfil no momento da venda, entao e
    ele — nao o cadastro de hoje — que diz se aquela nota podia sair.
    """
    return fiscal_profile_issues(
        item, crt=crt, subject=item.description or f"item {item.line_number}"
    )


def fiscal_invoice_issues(invoice, config):
    """Tudo que falta para os itens desta nota formarem uma NFC-e valida."""
    issues = []
    for item in invoice.items.all().order_by("line_number"):
        for issue in fiscal_item_issues(item, crt=config.crt):
            issues.append({**issue, "line_number": item.line_number, "product": str(item.product_id or "")})
    return issues
