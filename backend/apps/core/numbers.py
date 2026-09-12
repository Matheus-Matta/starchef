"""Conversão de número vindo do corpo da requisição, sem virar 500.

`Decimal(str(valor))` é a forma óbvia e a errada: `Decimal("dez reais")` levanta
`InvalidOperation`, que ninguém captura, e o cliente recebe "erro interno" por
ter digitado texto num campo de dinheiro. Um número absurdo (10³⁰) passa pela
conversão e só estoura no driver do banco, com `max_digits` estourado — outro
500, ainda mais longe da causa.

Aqui os dois casos viram `ValidationError`, que o handler da API
(`apps/core/exceptions.py`) converte em 400 com a mensagem no campo certo.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

#: Teto compatível com `max_digits=12, decimal_places=2` — o formato usado em
#: todo campo de dinheiro do projeto. Acima disso o INSERT falharia no banco.
MAX_MONEY = Decimal("9999999999.99")

#: Quantidade: `max_digits=10, decimal_places=3` nos itens de pedido.
MAX_QUANTITY = Decimal("9999999.999")

#: Peso da balança: `max_digits=9, decimal_places=3` em `ScaleReading`.
MAX_WEIGHT = Decimal("999999.999")

#: Faixa de um inteiro de 64 bits. O SQLite não declara faixa para
#: `PositiveIntegerField`, então o Django não anexa `MaxValueValidator` e o DRF
#: não tem o que herdar: um `10**30` atravessava a validação inteira e só
#: estourava no driver, como `OverflowError` (500). No Postgres o mesmo campo é
#: `integer` e o erro seria outro. O teto explícito vale nos dois.
MAX_SAFE_INTEGER = 9223372036854775807
MIN_SAFE_INTEGER = -9223372036854775808


def parse_decimal(
    value,
    *,
    field="valor",
    default=None,
    minimum=None,
    maximum=MAX_MONEY,
    allow_none=False,
):
    """Converte para `Decimal` ou levanta `ValidationError` explicando o campo.

    `default` é usado quando o valor vem ausente/vazio; sem ele e sem
    `allow_none`, campo ausente é erro — porque "não informou" e "informou
    zero" são coisas diferentes quando o assunto é dinheiro.
    """
    if value is None or (isinstance(value, str) and not value.strip()):
        if default is not None:
            return Decimal(str(default))
        if allow_none:
            return None
        raise ValidationError({field: "Informe um valor."})

    if isinstance(value, bool):
        # `True` vira Decimal("1") silenciosamente; num campo de dinheiro isso
        # é sempre erro de quem chamou, nunca intenção.
        raise ValidationError({field: "Informe um número."})

    try:
        parsed = Decimal(str(value).strip().replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError({field: "Informe um número válido."}) from None

    if not parsed.is_finite():
        raise ValidationError({field: "Informe um número válido."})
    if minimum is not None and parsed < minimum:
        raise ValidationError(
            {field: f"O valor não pode ser menor que {minimum.normalize()}."}
        )
    if maximum is not None and abs(parsed) > maximum:
        raise ValidationError({field: "O valor informado é grande demais."})
    return parsed


def parse_money(value, *, field="valor", default=None, allow_negative=False, allow_none=False):
    """Dinheiro: nunca negativo por padrão, sempre dentro do que a coluna aceita."""
    return parse_decimal(
        value,
        field=field,
        default=default,
        minimum=None if allow_negative else Decimal("0"),
        maximum=MAX_MONEY,
        allow_none=allow_none,
    )


def parse_quantity(value, *, field="quantity", default=None):
    """Quantidade: estritamente maior que zero e dentro do `max_digits` do item."""
    parsed = parse_decimal(
        value,
        field=field,
        default=default,
        minimum=None,
        maximum=MAX_QUANTITY,
    )
    if parsed <= 0:
        raise ValidationError({field: "A quantidade deve ser maior que zero."})
    return parsed


def fits_decimal(value, *, max_digits, decimal_places):
    """O valor cabe na coluna sem estourar `max_digits`?

    Django converte o `Decimal` na hora de gravar com um contexto de precisão
    igual a `max_digits`; um número maior que isso levanta `InvalidOperation`
    lá dentro, longe de quem o produziu. Perguntar antes deixa o erro nascer
    onde ele pode ser explicado.
    """
    if value is None:
        return True
    if not value.is_finite():
        return False
    teto = Decimal(10) ** (max_digits - decimal_places)
    return value.copy_abs() < teto
