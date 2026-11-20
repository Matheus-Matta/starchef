"""Leitura de INI no formato da ACBrLib — o documento que chega e as respostas.

As respostas da biblioteca (`NFE_Enviar`, `NFE_Consultar`…) vêm como INI com
seções `[Envio]`, `[Retorno]`, `[NFe<chave>]`; as chaves são lidas sem
diferenciar maiúscula, porque a lib não é consistente entre versões.
"""


def ler(texto):
    secoes, atual = {}, None
    for linha in (texto or "").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith(";"):
            continue
        if linha.startswith("[") and linha.endswith("]"):
            atual = secoes.setdefault(linha[1:-1].lower(), {})
            continue
        if atual is not None and "=" in linha:
            chave, valor = linha.split("=", 1)
            atual[chave.strip().lower()] = valor.strip()
    return secoes


def primeira(secoes, *nomes_ou_prefixos):
    """A primeira seção cujo nome bate (ou começa com) um dos informados."""
    for alvo in nomes_ou_prefixos:
        alvo = alvo.lower()
        for nome, campos in secoes.items():
            if nome == alvo or nome.startswith(alvo):
                return campos
    return {}


#: Seção do item no INI → (campo do código, quantos dígitos ele tem).
_CODIGOS = {"pis": ("CST", 2), "cofins": ("CST", 2), "icms": ("CST", 2)}
_CSOSN = 3


def completar_codigos(texto):
    """O INI com o zero à esquerda do CST de volta: "CST=4" → "CST=04".

    Produção, 20/11/2026: "Valor string inválido para TCSTPIS: 4". O perfil
    fiscal passou pelo Excel, que apaga o zero do código. O backend já completa
    (`codigos_fiscais.py`), mas o comunicador atende qualquer backend — inclusive
    um servidor de loja que ainda não atualizou —, e a lib recusa a nota inteira
    por um zero. Só mexe em dígitos mais curtos que o código.
    """
    linhas, secao = [], ""
    for linha in (texto or "").splitlines():
        limpa = linha.strip()
        if limpa.startswith("[") and limpa.endswith("]"):
            secao = limpa[1:-1].rstrip("0123456789").lower()
        elif "=" in limpa:
            chave, valor = (parte.strip() for parte in limpa.split("=", 1))
            campo, tamanho = _CODIGOS.get(secao, ("", 0))
            if secao == "icms" and chave.upper() == "CSOSN":
                campo, tamanho = "CSOSN", _CSOSN
            if campo and chave.upper() == campo and valor.isdigit() and len(valor) < tamanho:
                linha = f"{chave}={valor.zfill(tamanho)}"
        linhas.append(linha)
    return "\n".join(linhas)
