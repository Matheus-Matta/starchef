from rest_framework import serializers

# Campos que o cliente nunca define — sempre read-only nos serializers.
# Fonte unica de verdade para evitar repetir a mesma lista em cada Meta.
TIMESTAMP_READ_ONLY_FIELDS = ["id", "created_at", "updated_at"]
AUDIT_READ_ONLY_FIELDS = [*TIMESTAMP_READ_ONLY_FIELDS, "created_by", "updated_by"]


class MoneyField(serializers.DecimalField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("decimal_places", 2)
        super().__init__(*args, **kwargs)


class TenantModelSerializer(serializers.ModelSerializer):
    """Serializer base multi-tenant.

    Expoe `account` como read-only e valida, no `validate`, que todo objeto
    relacionado informado pertence a mesma conta/restaurante/filial do usuario —
    barrando referencias cruzadas entre tenants.
    """

    account = serializers.PrimaryKeyRelatedField(read_only=True)

    def get_fields(self):
        fields = super().get_fields()
        # `restaurant` e `branch` são preenchidos no servidor (perform_create os
        # herda do perfil quando omitidos). Constraints de unicidade por filial
        # fazem o DRF marcá-los como obrigatórios indevidamente — o que gera um
        # "Este campo é obrigatório" que não aparece em nenhum campo do formulário
        # (eles não são exibidos). Aqui garantimos que sejam opcionais no input.
        if "restaurant" in fields:
            # required=False + allow_null: o front pode enviar null (escopo "Todos"
            # sem seleção); o perform_create resolve pelo perfil ou devolve um erro
            # claro pedindo para selecionar um restaurante.
            fields["restaurant"].required = False
            fields["restaurant"].allow_null = True
        if "branch" in fields:
            # default=None faz o UniqueTogetherValidator (constraints por filial)
            # parar de exigir `branch` no input; quando omitido, fica nulo (o campo
            # é nullable no model) e o front continua enviando a filial do perfil.
            fields["branch"].required = False
            fields["branch"].allow_null = True
            fields["branch"].default = None
        return fields

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

        from apps.core.access import is_tenant_admin

        account_id = request.account.id
        profile = getattr(request.user, "profile", None)
        enforce_restaurant = bool(profile and profile.restaurant_id and not is_tenant_admin(request.user))
        enforce_branch = bool(profile and profile.branch_id and not is_tenant_admin(request.user))

        # Restaurante DESTE registro (payload ou instance). Objetos relacionados
        # que pertencem a um restaurante têm de ser do MESMO restaurante — bloqueia,
        # p.ex., vincular uma mesa do restaurante A a um setor do restaurante B
        # (vale inclusive para admin). Compartilhados (restaurant=None) não afetam.
        own_restaurant = attrs.get("restaurant") or getattr(self.instance, "restaurant", None)
        own_restaurant_id = getattr(own_restaurant, "id", None)
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
                related_restaurant_id = getattr(related, "restaurant_id", None)
                related_label = related._meta.label if hasattr(related, "_meta") else None
                if related_restaurant_id is None and related_label == "restaurants.Restaurant":
                    related_restaurant_id = related.id
                if enforce_restaurant and related_restaurant_id and related_restaurant_id != profile.restaurant_id:
                    errors[field_name] = "Objeto relacionado pertence a outro restaurante."
                    break
                # Bloqueio universal (inclusive admin): relacionado de outro restaurante.
                if (
                    field_name != "restaurant"
                    and own_restaurant_id
                    and related_restaurant_id
                    and related_restaurant_id != own_restaurant_id
                ):
                    errors[field_name] = "Objeto relacionado pertence a outro restaurante."
                    break
                related_branch_id = getattr(related, "branch_id", None)
                if related_branch_id is None and related_label == "restaurants.Branch":
                    related_branch_id = related.id
                if enforce_branch and related_branch_id and related_branch_id != profile.branch_id:
                    errors[field_name] = "Objeto relacionado pertence a outra filial."
                    break

        if errors:
            raise serializers.ValidationError(errors)

        return attrs
