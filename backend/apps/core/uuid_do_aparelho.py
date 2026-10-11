"""O UUID que o aparelho dá ao registro antes de enviar.

Loja e nuvem aceitam escrever; o terminal desvia quando uma cai. Quando a loja
grava e morre antes de responder, o aparelho não tem como saber que chegou e
manda à outra ponta. Com o mesmo UUID nas duas, a sincronização junta as linhas
pelo id: um registro só. A única regra fixa é que o UUID nunca muda.
"""
import uuid

from django.core.exceptions import ValidationError


def ler(valor, rotulo="registro"):
    """O UUID do corpo da requisição, `None` se não veio. Malformado é 400."""
    if valor in (None, ""):
        return None
    try:
        return uuid.UUID(str(valor))
    except ValueError as exc:
        raise ValidationError(f"Identificador do {rotulo} inválido.") from exc
