"""As linhas de item que a comanda da pesagem imprime abaixo do cabeçalho.

É a lista do restaurante (bebidas, sobremesa...) que o atendente marca à mão
no papel. Cada linha é um PRODUTO do cardápio ou uma linha EM BRANCO, para
escrever o que não está na lista. As em branco saem sempre no fim.

Fica no restaurante, e não no terminal: todas as balanças da casa imprimem o
mesmo papel, e a lista sincroniza loja ⇄ nuvem junto com o resto do cadastro.

Formato gravado (o mesmo que a API recebe e devolve):

    [{"tipo": "produto", "produto": "<uuid>"}, {"tipo": "branco"}]
"""
import uuid

from rest_framework import serializers

TIPO_PRODUTO = "produto"
TIPO_BRANCO = "branco"

# Teto de papel, não de regra: cada linha é uma linha impressa, e uma comanda
# de meio metro ninguém usa.
MAXIMO_DE_LINHAS = 20


def validar_linhas_da_comanda(valor):
    """Normaliza a lista; recusa (400) o que não é produto nem linha em branco."""
    if valor in (None, ""):
        return []
    if not isinstance(valor, list):
        raise serializers.ValidationError("Envie uma lista de linhas.")
    if len(valor) > MAXIMO_DE_LINHAS:
        raise serializers.ValidationError(
            f"A comanda aceita no máximo {MAXIMO_DE_LINHAS} linhas."
        )
    linhas = []
    for linha in valor:
        tipo = linha.get("tipo") if isinstance(linha, dict) else None
        if tipo == TIPO_BRANCO:
            linhas.append({"tipo": TIPO_BRANCO})
            continue
        if tipo != TIPO_PRODUTO:
            raise serializers.ValidationError(
                "Cada linha é um produto ou uma linha em branco."
            )
        try:
            produto = str(uuid.UUID(str(linha.get("produto"))))
        except (TypeError, ValueError, AttributeError):
            raise serializers.ValidationError("Produto inválido na linha da comanda.") from None
        linhas.append({"tipo": TIPO_PRODUTO, "produto": produto})
    return linhas
