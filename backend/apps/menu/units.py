"""Conversao entre a unidade escrita na ficha tecnica e a unidade do insumo.

O estoque raciocina em unidade base — grama para peso, mililitro para volume,
unidade para item discreto. A ficha tecnica, porem, e escrita na unidade que a
cozinha usa ("0,03 kg de queijo"), e o insumo pode estar cadastrado em outra
("g"). Sem converter, 0,03 kg baixava 0,03 g do saldo: mil vezes menos do que
saiu de verdade da geladeira, e o inventario nunca fechava.

Conversao entre grandezas diferentes NAO existe aqui de proposito. Litro para
grama depende da densidade do que esta dentro do recipiente, que o cadastro
nao conhece; inventar um fator generico produziria um numero plausivel e
errado. Melhor recusar e obrigar o cadastro a se acertar.
"""
from decimal import Decimal

WEIGHT = "weight"
VOLUME = "volume"
COUNT = "count"

# unidade -> (grandeza, quanto vale na unidade base da grandeza)
_UNITS = {
    "kg": (WEIGHT, Decimal("1000")),
    "g": (WEIGHT, Decimal("1")),
    "l": (VOLUME, Decimal("1000")),
    "ml": (VOLUME, Decimal("1")),
    "unit": (COUNT, Decimal("1")),
}

#: Unidade base de cada grandeza — o que o saldo de estoque guarda.
BASE_UNIT = {WEIGHT: "g", VOLUME: "ml", COUNT: "unit"}


class IncompatibleUnitError(ValueError):
    """Uma conversao entre grandezas que nao se convertem sozinhas."""


def dimension_of(unit):
    """A grandeza da unidade (`weight`, `volume` ou `count`)."""
    try:
        return _UNITS[unit][0]
    except KeyError:
        raise IncompatibleUnitError(f"Unidade desconhecida: {unit!r}.") from None


def base_unit_of(unit):
    """A unidade base da grandeza a que `unit` pertence."""
    return BASE_UNIT[dimension_of(unit)]


def convert(quantity, from_unit, to_unit):
    """`quantity`, escrita em `from_unit`, expressa em `to_unit`.

    Levanta `IncompatibleUnitError` quando as unidades sao de grandezas
    diferentes — o chamador decide se isso vira erro de validacao para o
    operador ou se a linha e ignorada.
    """
    if from_unit == to_unit:
        return Decimal(str(quantity))

    source_dimension, source_factor = _resolve(from_unit)
    target_dimension, target_factor = _resolve(to_unit)
    if source_dimension != target_dimension:
        raise IncompatibleUnitError(
            f"Nao e possivel converter {from_unit} em {to_unit}: grandezas diferentes "
            f"({source_dimension} e {target_dimension})."
        )

    return Decimal(str(quantity)) * source_factor / target_factor


def _resolve(unit):
    try:
        return _UNITS[unit]
    except KeyError:
        raise IncompatibleUnitError(f"Unidade desconhecida: {unit!r}.") from None
