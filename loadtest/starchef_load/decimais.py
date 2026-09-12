r"""Casas decimais que o schema permite.

O drf-spectacular descreve um `DecimalField(max_digits=5, decimal_places=1)`
como `pattern: ^-?\d{0,5}(?:\.\d{0,1})?$`. Um valor com casas demais leva 400
— e esse 400 e do gerador, nao do backend. O payload limpo respeita o padrao; o
desleixado continua mandando casas demais de proposito.
"""
import re

#: Captura (max_digits, decimal_places) do pattern acima.
_PADRAO = re.compile(r"\\d\{0,(\d+)\}\(\?:\\\.\\d\{0,(\d+)\}")


def decimal_within(meta, valor, limpo=True):
    encontrado = _PADRAO.search(meta.get("pattern") or "")
    if not encontrado or not limpo:
        return valor
    digitos, casas = int(encontrado.group(1)), int(encontrado.group(2))
    teto = 10 ** max(digitos - casas, 1) - 1
    return round(min(float(valor), teto), casas)
