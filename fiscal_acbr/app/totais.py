"""Os totais de ICMS/PIS/COFINS do INI, quando o backend não os mandou.

Produção, 20/11/2026, primeira venda em Regime Normal: "602 Rejeicao: Total do
PIS difere do somatorio dos itens sujeitos ao ICMS". O backend até a 3.1.20
mandava a seção `[Total]` sem vBC/vICMS/vPIS/vCOFINS, e a lib os gravava
zerados — no Simples batia por acaso, porque todo imposto destacado é zero.

O backend novo já manda (`acbrlib/ini_impostos.py`) e aqui nada muda: o total
que veio é a autoridade. Este é o socorro para o servidor de loja que atualizou
só o comunicador. A conta é a mesma: a soma dos itens, e o ICMS só dos CST
cujo grupo tem `vICMS` (o ICMS60 não tem — somá-lo daria a 532).
"""
from decimal import Decimal, InvalidOperation

CST_COM_ICMS = {"00", "10", "20", "51", "70", "90"}
CSOSN_COM_ICMS = {"900"}


def _numero(valor):
    try:
        return Decimal(str(valor or "0").strip())
    except InvalidOperation:
        return Decimal("0")


def _somas(linhas):
    somas = dict.fromkeys(("vBC", "vICMS", "vPIS", "vCOFINS"), Decimal("0.00"))
    secao, icms = "", {}

    def fechar_icms():
        situacao = icms.get("CST") or icms.get("CSOSN") or ""
        if situacao in CST_COM_ICMS | CSOSN_COM_ICMS:
            somas["vBC"] += _numero(icms.get("vBC"))
            somas["vICMS"] += _numero(icms.get("vICMS"))

    for linha in linhas:
        limpa = linha.strip()
        if limpa.startswith("[") and limpa.endswith("]"):
            if secao == "icms":
                fechar_icms()
            secao, icms = limpa[1:-1].rstrip("0123456789").lower(), {}
        elif "=" in limpa:
            chave, valor = (parte.strip() for parte in limpa.split("=", 1))
            if secao == "icms":
                icms[chave] = valor
            elif secao in ("pis", "cofins") and chave == f"v{secao.upper()}":
                somas[chave] += _numero(valor)
    if secao == "icms":
        fechar_icms()
    return somas


def completar_totais(texto):
    """O INI com os totais que faltavam na `[Total]`; o que veio fica."""
    linhas = (texto or "").splitlines()
    inicio = next((i for i, linha in enumerate(linhas) if linha.strip().lower() == "[total]"), None)
    if inicio is None:
        return texto
    fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i].strip().startswith("[")),
               len(linhas))
    presentes = {linha.split("=", 1)[0].strip() for linha in linhas[inicio + 1:fim] if "=" in linha}
    faltando = [f"{chave}={valor:.2f}" for chave, valor in _somas(linhas).items()
                if chave not in presentes]
    return "\n".join(linhas[:inicio + 1] + faltando + linhas[inicio + 1:])
