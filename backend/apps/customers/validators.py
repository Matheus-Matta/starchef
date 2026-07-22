"""Validação de CPF (padrão brasileiro) — Sprint 4 · STC-042/043."""
import re


def strip_cpf(value):
    return re.sub(r"\D", "", value or "")


def is_valid_cpf(value):
    """True se `value` for um CPF válido (11 dígitos + dígitos verificadores)."""
    cpf = strip_cpf(value)
    if len(cpf) != 11 or cpf == cpf[0] * 11:
        return False

    for length in (9, 10):
        digits = cpf[:length]
        expected = _check_digit(digits)
        if int(cpf[length]) != expected:
            return False
    return True


def _check_digit(digits):
    weight = len(digits) + 1
    total = sum(int(d) * (weight - i) for i, d in enumerate(digits))
    remainder = (total * 10) % 11
    return 0 if remainder == 10 else remainder


def format_cpf(value):
    cpf = strip_cpf(value)
    if len(cpf) != 11:
        return value
    return f"{cpf[:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:]}"


def mask_cpf(value):
    """Oculta parcialmente o CPF: 123.***.**9-** (para listagens sem permissão)."""
    cpf = strip_cpf(value)
    if len(cpf) != 11:
        return "***" if value else ""
    return f"{cpf[:3]}.***.***-**"


def mask_phone(value):
    digits = re.sub(r"\D", "", value or "")
    if len(digits) < 4:
        return "***" if value else ""
    return f"{digits[:2]}****{digits[-2:]}"
