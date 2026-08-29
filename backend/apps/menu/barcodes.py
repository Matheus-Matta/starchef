"""Códigos de barras de produto (GTIN) — normalização e validação.

O PDV precisa achar UM produto a partir do que o leitor mandou. Duas coisas
tornam isso frágil se não forem tratadas aqui:

* **zeros à esquerda.** `0000012345670` e `12345670` são códigos diferentes.
  Guardar como número perderia os zeros e faria o scanner não achar o produto —
  por isso o campo é texto, e a normalização só remove separadores.
* **dígito verificador.** Um código digitado errado costuma passar por
  "parece um EAN" e só falha na hora da venda. Conferir o dígito no cadastro
  transforma um erro de operação em um erro de digitação, que é onde ele
  pode ser corrigido.

A validação é OPCIONAL de propósito: há etiquetas internas e códigos de
balança que não são GTIN. Um valor fora dos comprimentos conhecidos é aceito
como código livre; um valor COM comprimento de GTIN precisa ter o dígito
verificador certo, senão o cadastro estaria guardando um engano.
"""

# Comprimentos que o padrão GS1 reconhece: EAN-8, UPC-A, EAN-13 e GTIN-14.
GTIN_LENGTHS = (8, 12, 13, 14)


def normalize_barcode(value):
    """Deixa só os dígitos, preservando zeros à esquerda.

    Leitores costumam anexar espaços, hífens ou um sufixo de quebra de linha;
    nada disso faz parte do código.
    """
    return "".join(character for character in str(value or "") if character.isdigit())


def gtin_check_digit(digits):
    """Dígito verificador GS1 (módulo 10) para o corpo do código."""
    total = 0
    # Da direita para a esquerda, os pesos alternam 3 e 1 — a mesma conta
    # para EAN-8, UPC-12, EAN-13 e GTIN-14.
    for position, character in enumerate(reversed(digits)):
        weight = 3 if position % 2 == 0 else 1
        total += int(character) * weight
    return (10 - total % 10) % 10


def is_valid_gtin(value):
    """True quando o valor tem comprimento de GTIN e dígito verificador certo."""
    digits = normalize_barcode(value)
    if len(digits) not in GTIN_LENGTHS:
        return False
    return gtin_check_digit(digits[:-1]) == int(digits[-1])


def looks_like_gtin(value):
    """O valor tem cara de GTIN? (comprimento conhecido e só dígitos)"""
    digits = normalize_barcode(value)
    return len(digits) in GTIN_LENGTHS and digits == str(value or "").strip()
