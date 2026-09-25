"""O campo `metafields` como a API o aceita.

Existe porque `JSONField` do DRF aceita QUALQUER JSON, e este campo é escrito por
um app na mão de um garçom. Sem a porta estreita, um PATCH grava megabytes,
estrutura aninhada que nenhum relatório consegue agrupar e `operator_code: "abc"`
num campo que existe para ser contado.

A regra mora em `apps.core.metafields` (formato) e em
`apps.orders.operator_code` (o código só aceita números). Aqui é só a tradução
para o erro que o DRF devolve ao cliente.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers


class MetafieldsField(serializers.JSONField):
    """Normaliza e recusa com a mensagem que o app mostra ao operador."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        # O import é aqui dentro de propósito: `apps.restaurants` usa este campo
        # na comanda, e importar `apps.orders` no topo fecharia um ciclo entre os
        # dois módulos de serializer.
        from apps.orders.operator_code import preparar

        bruto = super().to_internal_value(data)
        try:
            return preparar(bruto, campo=self.field_name or "metafields")
        except DjangoValidationError as falha:
            # `ValidationError` do Django carrega `{campo: [mensagens]}`. Passar o
            # objeto cru ao DRF produziria um corpo aninhado que o app não lê.
            mensagens = getattr(falha, "message_dict", None)
            if mensagens:
                raise serializers.ValidationError(
                    [texto for lista in mensagens.values() for texto in lista]
                ) from falha
            raise serializers.ValidationError(falha.messages) from falha
