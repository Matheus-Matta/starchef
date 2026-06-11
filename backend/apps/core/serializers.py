from rest_framework import serializers


class MoneyField(serializers.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)


class TenantModelSerializer(serializers.ModelSerializer):
    account = serializers.PrimaryKeyRelatedField(read_only=True)

    def _iter_values(self, value):
        if value is None:
            return []
        if isinstance(value, (list, tuple, set)):
            return value
        if hasattr(value, "all"):
            return value.all()
        return [value]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        request = self.context.get("request")
        if not request or not getattr(request, "account", None):
            return attrs

        account_id = request.account.id
        payload_account_id = self.initial_data.get("account") or self.initial_data.get("account_id")
        if payload_account_id and str(payload_account_id) != str(account_id):
            raise serializers.ValidationError(
                {"account_id": "Nao e permitido informar uma conta diferente da conta autenticada."}
            )

        errors = {}
        for field_name, value in attrs.items():
            for related in self._iter_values(value):
                related_account_id = getattr(related, "account_id", None)
                if related_account_id is not None and related_account_id != account_id:
                    errors[field_name] = "Objeto relacionado pertence a outra conta."
                    break

        if errors:
            raise serializers.ValidationError(errors)

        return attrs
