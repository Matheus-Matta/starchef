from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.cardapio_consumo.agenda import descricao, proximas_datas
from apps.cardapio_consumo.models import CardapioConsumo, ExecucaoCardapio, ItemCardapioConsumo
from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.menu.units import IncompatibleUnitError, convert

_HERDADOS = ("account", "restaurant", "branch", "created_by", "updated_by")


class ItemCardapioConsumoSerializer(TenantModelSerializer):
    nome = serializers.SerializerMethodField()
    unidade_do_insumo = serializers.CharField(source="ingredient.unit", read_only=True, default="")

    class Meta:
        model = ItemCardapioConsumo
        fields = ["id", "ingredient", "product", "quantidade", "unidade", "nome", "unidade_do_insumo"]

    def get_nome(self, item):
        return (item.ingredient or item.product).name

    def validate(self, data):
        data = super().validate(data)  # insumo e produto da MESMA conta
        ingredient, product = data.get("ingredient"), data.get("product")
        if bool(ingredient) == bool(product):
            raise serializers.ValidationError("Cada linha é um insumo OU um produto.")
        if data.get("quantidade") is None or data["quantidade"] <= 0:
            raise serializers.ValidationError({"quantidade": "Informe uma quantidade maior que zero."})
        if ingredient and data.get("unidade"):
            try:
                convert(data["quantidade"], data["unidade"], ingredient.unit)
            except IncompatibleUnitError as exc:
                raise serializers.ValidationError(
                    {"unidade": f"{data['unidade']} não converte para {ingredient.unit} ({ingredient.name})."}
                ) from exc
        if product:
            data["unidade"] = ""
        return data


class CardapioConsumoSerializer(TenantModelSerializer):
    itens = ItemCardapioConsumoSerializer(many=True)
    local_nome = serializers.CharField(source="local.name", read_only=True)
    proximas_datas = serializers.SerializerMethodField()
    quando = serializers.SerializerMethodField()

    class Meta:
        model = CardapioConsumo
        fields = ["id", "nome", "frequencia", "dias_da_semana", "dia_do_mes", "horario", "local", "local_nome", "quando",
                  "confirma_sozinho", "comeca_em", "ativo", "observacoes", "itens", "proximas_datas",
                  "restaurant", "branch", "created_at", "updated_at"]
        read_only_fields = ["restaurant", "branch", *AUDIT_READ_ONLY_FIELDS]

    def get_quando(self, cardapio):
        return descricao(cardapio)

    def get_proximas_datas(self, cardapio):
        return [data.isoformat() for data in proximas_datas(cardapio, timezone.localdate())]

    def validate_dias_da_semana(self, dias):
        if not isinstance(dias, list) or any(not isinstance(dia, int) or not 0 <= dia <= 6 for dia in dias):
            raise serializers.ValidationError("Use os dias de 0 (segunda) a 6 (domingo).")
        return sorted(set(dias))

    def validate(self, data):
        data = super().validate(data)  # local da MESMA conta
        frequencia = data.get("frequencia", getattr(self.instance, "frequencia", CardapioConsumo.DIARIA))
        dias = data.get("dias_da_semana", getattr(self.instance, "dias_da_semana", []))
        dia_do_mes = data.get("dia_do_mes", getattr(self.instance, "dia_do_mes", None))
        if frequencia == CardapioConsumo.SEMANAL and not dias:
            raise serializers.ValidationError({"dias_da_semana": "Escolha ao menos um dia da semana."})
        if frequencia == CardapioConsumo.MENSAL and not dia_do_mes:
            raise serializers.ValidationError({"dia_do_mes": "Escolha o dia do mês (1 a 31)."})
        if "itens" in data and not data["itens"]:
            raise serializers.ValidationError({"itens": "Adicione ao menos um insumo ou produto."})
        if data.get("local"):
            data["restaurant"], data["branch"] = data["local"].restaurant, data["local"].branch
        return data

    def _gravar_itens(self, cardapio, itens):
        ItemCardapioConsumo.all_objects.filter(cardapio=cardapio).delete()
        for item in itens:
            for campo in _HERDADOS:
                item.pop(campo, None)
            ItemCardapioConsumo.objects.create(
                cardapio=cardapio, account=cardapio.account, restaurant=cardapio.restaurant,
                branch=cardapio.branch, created_by=cardapio.updated_by, updated_by=cardapio.updated_by, **item,
            )

    @transaction.atomic
    def create(self, validated_data):
        itens = validated_data.pop("itens", [])
        cardapio = super().create(validated_data)
        self._gravar_itens(cardapio, itens)
        return cardapio

    @transaction.atomic
    def update(self, instance, validated_data):
        itens = validated_data.pop("itens", None)
        cardapio = super().update(instance, validated_data)
        if itens is not None:
            self._gravar_itens(cardapio, itens)
        return cardapio


class ExecucaoCardapioSerializer(serializers.ModelSerializer):
    situacao_label = serializers.CharField(source="get_situacao_display", read_only=True)

    class Meta:
        model = ExecucaoCardapio
        fields = ["id", "data", "situacao", "situacao_label", "saida", "faltas", "mensagem", "created_at"]
