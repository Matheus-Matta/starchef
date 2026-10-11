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
