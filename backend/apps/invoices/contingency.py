"""Quando uma falha de emissão justifica contingência — e quando não justifica.

A regra, em uma frase: **contingência é para indisponibilidade, nunca para
recusa.**

Contingência (tpEmis=9) existe para o caso em que não se consegue FALAR com o
autorizador. Uma rejeição é o oposto: a SEFAZ falou, analisou o documento e
disse que ele está errado. Emitir o mesmo documento errado em contingência não
conserta nada — entrega um cupom ao cliente e cria um documento irregular no
CNPJ, que depois só se resolve cancelando, um a um, dentro do prazo.

O caso real que motivou este módulo: "Código Regime Tributário do emitente
diverge do cadastro na Receita Federal". Em contingência essa nota sairia
igualmente errada, só que com o cliente já com o papel na mão.

Duas decisões de projeto que valem ser explícitas:

**Falha desconhecida NÃO justifica contingência.** A classificação falha
fechada. Uma exceção nova que ninguém classificou é tratada como documento
inválido, não como rede caindo — porque emitir à toa é irreversível e não
emitir não é.

**A classificação é exaustiva e cobrada por teste.** Toda subclasse de
`FiscalProviderError` precisa estar em um dos dois conjuntos abaixo. Adicionar
uma exceção sem classificá-la quebra a suíte, e não a operação de uma loja.
"""
from apps.invoices.providers import (
    FiscalAmbiguous,
    FiscalConfigurationError,
    FiscalNotFound,
    FiscalProviderError,
    FiscalRejection,
    FiscalUnavailable,
)

#: Classificações possíveis de uma falha de emissão.
INDISPONIBILIDADE = "indisponibilidade"
DOCUMENTO_INVALIDO = "documento_invalido"
DESCONHECIDA = "desconhecida"

#: Não consegui FALAR com o autorizador. A única família que justifica
#: contingência — e a única que justifica retentativa automática.
FALHAS_DE_INDISPONIBILIDADE = (FiscalUnavailable,)

#: Falei, e o documento (ou o cadastro) está errado. Repetir em contingência
#: repete o erro com o cupom já entregue.
FALHAS_DE_DOCUMENTO = (
    FiscalRejection,
    FiscalConfigurationError,
    # `FiscalNotFound` e `FiscalAmbiguous` também não justificam, por um motivo
    # diferente e igualmente sério: nos dois casos o estado do documento no
    # provedor é DESCONHECIDO. Emitir outro em contingência é o caminho mais
    # curto para duplicar documento fiscal.
    FiscalNotFound,
    FiscalAmbiguous,
)

#: Por que a contingência não se aplica, em português, para o operador.
_MOTIVOS = {
    FiscalRejection: (
        "a nota foi recusada na análise — contingência repetiria a mesma recusa, "
        "com o cupom já entregue ao cliente"
    ),
    FiscalConfigurationError: (
        "o cadastro fiscal está inválido — nenhuma nota da empresa sai, em "
        "contingência ou fora dela, enquanto não for corrigido"
    ),
    FiscalNotFound: (
        "o provedor não conhece esta nota — emitir outra agora é o caminho para "
        "duplicar documento fiscal"
    ),
    FiscalAmbiguous: (
        "não se sabe se a nota já foi emitida — emitir outra agora é o caminho "
        "para duplicar documento fiscal"
    ),
}


def classificar(erro):
    """`INDISPONIBILIDADE`, `DOCUMENTO_INVALIDO` ou `DESCONHECIDA`."""
    if isinstance(erro, FALHAS_DE_INDISPONIBILIDADE):
        return INDISPONIBILIDADE
    if isinstance(erro, FALHAS_DE_DOCUMENTO):
        return DOCUMENTO_INVALIDO
    return DESCONHECIDA


def justifica_contingencia(erro):
    """A única porta para tpEmis=9. Falha fechada de propósito.

    Quem for implementar emissão em contingência — no terminal ou onde for —
    precisa passar por aqui. É o que impede a regra de se perder de novo entre
    os vários blocos de `except` espalhados pelo serviço de emissão.
    """
    return classificar(erro) == INDISPONIBILIDADE


def motivo_da_recusa(erro):
    """Por que esta falha NÃO vira contingência. Vazio quando ela vira."""
    if justifica_contingencia(erro):
        return ""
    for classe, texto in _MOTIVOS.items():
        if isinstance(erro, classe):
            return f"Contingência não se aplica: {texto}."
    return (
        "Contingência não se aplica: a falha não foi classificada como "
        "indisponibilidade, e emitir sem saber a causa é irreversível."
    )


def subclasses_de_falha():
    """Toda a árvore de `FiscalProviderError`, para o teste de cobertura."""
    encontradas = set()
    pendentes = [FiscalProviderError]
    while pendentes:
        classe = pendentes.pop()
        for filha in classe.__subclasses__():
            if filha not in encontradas:
                encontradas.add(filha)
                pendentes.append(filha)
    return encontradas
