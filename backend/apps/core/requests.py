"""Leitura de campo obrigatório do corpo, sem virar 500.

`request.data["campo"]` é a forma idiomática e a insegura: o corpo vem do
cliente, e um campo ausente levanta `KeyError`, que ninguém captura. O handler
da API traduz isso para "Ocorreu um erro interno" — a mensagem errada para um
erro de preenchimento, e um 500 que o PDV trata como falha TEMPORÁRIA,
devolvendo a operação à fila para tentar de novo para sempre em vez de mandá-la
para a tela de revisão.

`required_field` faz a mesma leitura levantando `ValidationError`, que o
handler converte em 400 com a mensagem no campo certo.
"""
from django.core.exceptions import ValidationError

VAZIOS = (None, "")


def required_field(request, name, message=None, *, allow_blank=False):
    """Devolve `request.data[name]` ou levanta `ValidationError` explicando."""
    data = request.data if hasattr(request.data, "get") else {}
    value = data.get(name)
    if value in VAZIOS and not (allow_blank and value == ""):
        raise ValidationError({name: message or "Este campo é obrigatório."})
    return value
