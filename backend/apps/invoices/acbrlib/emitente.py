"""Quem emite a nota da ACBrLib: o cadastro fiscal, completado pelo restaurante.

Na Focus o emitente já mora no painel dela e basta o CNPJ. Aqui o XML inteiro
nasce no backend, e o `FiscalConfig` só copiava o cadastro do restaurante ao
ser CRIADO (`services.ensure_fiscal_config`). Endereço preenchido depois, no
restaurante, nunca chegava à nota: a SEFAZ recusava por bairro ou CEP vazio.

A regra é a mesma da página fiscal: o que ela tem vale (a razão social
ajustada ali não é desfeita); o que está em branco vem do restaurante na hora
da emissão. O que falta nos dois é dito ANTES de ir à SEFAZ, pelo nome.
"""
#: O mínimo que o grupo `emit` do XML exige, com o nome que o operador conhece.
OBRIGATORIOS = {
    "cnpj": "CNPJ",
    "ie": "Inscrição Estadual",
    "corporate_name": "Razão social",
    "address_line": "Logradouro",
    "district": "Bairro",
    "city": "Município",
    "city_ibge": "Código IBGE do município",
    "uf": "UF",
    "zip_code": "CEP",
}


class Emitente:
    """Os campos do emitente, lidos como `config.<campo>`."""

    def __init__(self, config):
        # Import tardio: `services` registra os provedores ao ser importado.
        from apps.invoices.services import _EMITTER_FIELDS_FROM_RESTAURANT as DO_RESTAURANTE

        restaurante = config.restaurant or getattr(config.branch, "restaurant", None)
        self._valores = {}
        for campo in {*OBRIGATORIOS, "trade_name", "address_number", "crt"}:
            valor = getattr(config, campo, "") or ""
            if isinstance(valor, str):
                valor = valor.strip()
            if not valor and restaurante is not None and campo in DO_RESTAURANTE:
                valor = (DO_RESTAURANTE[campo](restaurante) or "").strip()
            self._valores[campo] = valor

    def __getattr__(self, campo):
        try:
            return self.__dict__["_valores"][campo]
        except KeyError as erro:
            raise AttributeError(campo) from erro

    def faltando(self):
        return [rotulo for campo, rotulo in OBRIGATORIOS.items() if not self._valores.get(campo)]
