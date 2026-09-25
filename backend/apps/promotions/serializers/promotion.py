from rest_framework import serializers

from apps.core.serializers import AUDIT_READ_ONLY_FIELDS, TenantModelSerializer
from apps.promotions.models import DiscountTable, Promotion, PromotionProduct


class PromotionProductSerializer(TenantModelSerializer):
    """O vínculo regra↔produto com o "de/por" próprio."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    # O preço do cadastro viaja junto para a tela poder mostrar, ao lado do
    # "de 30 por 15", que o produto está cadastrado a 20 — sem isso o operador
    # digita o encarte às cegas.
    product_base_price = serializers.DecimalField(
        source="product.base_price", max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = PromotionProduct
        fields = [
            "id",
            "product",
            "product_name",
            "product_base_price",
            "promotional_price",
            "compare_at_price",
        ]


class PromotionSerializer(TenantModelSerializer):
    """Uma regra da tabela, com os produtos que ela alcança.

    Os produtos entram e saem AQUI, no mesmo salvamento da regra: são a regra,
    e não um cadastro à parte. Exigir uma segunda chamada para vinculá-los
    deixaria regras vazias pelo caminho — vazias e ativas, que é o pior estado:
    aparecem na lista como promoção e não descontam nada.
    """

    product_links = PromotionProductSerializer(many=True, required=False)
    is_active = serializers.BooleanField(read_only=True)
    table_name = serializers.CharField(source="table.name", read_only=True)

    class Meta:
        model = Promotion
        fields = "__all__"
        read_only_fields = [*AUDIT_READ_ONLY_FIELDS, "products"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        alvo = attrs.get("target_type", getattr(self.instance, "target_type", Promotion.TARGET_PRODUCTS))
        tipo = attrs.get("discount_kind", getattr(self.instance, "discount_kind", Promotion.KIND_PERCENT))
        valor = attrs.get("discount_value", getattr(self.instance, "discount_value", 0))
        if tipo == Promotion.KIND_PERCENT and valor > 100:
            raise serializers.ValidationError(
                {"discount_value": "Um desconto percentual não passa de 100%."}
            )
        links = attrs.get("product_links")
        if alvo == Promotion.TARGET_PRODUCTS and links is not None and not links:
            raise serializers.ValidationError(
                {"product_links": "Escolha ao menos um produto, ou mude o alvo da regra."}
            )
        if links:
            self._recusar_conflito_na_tabela(attrs, links)
        return attrs

    def _recusar_conflito_na_tabela(self, attrs, links):
        """Dois descontos para o mesmo produto na MESMA tabela é erro, não regra.

        Dentro de uma tabela a prioridade é a posição, então tecnicamente o
        segundo vínculo nunca venceria — ele ficaria ali, invisível, parecendo
        ativo. Quem cadastrou juraria ter dado 30% e o caixa cobraria 10%.
        Entre tabelas DIFERENTES o conflito é legítimo e se resolve pela mais
        antiga, como o cliente espera.
        """
        tabela = attrs.get("table") or getattr(self.instance, "table", None)
        if tabela is None:
            return
        ids = [link["product"].pk for link in links if link.get("product")]
        if not ids:
            return
        ocupados = PromotionProduct.all_objects.filter(
            promotion__table_id=tabela.pk,
            product_id__in=ids,
            deleted_at__isnull=True,
        ).exclude(promotion_id=getattr(self.instance, "pk", None))
        conflito = ocupados.select_related("product", "promotion").first()
        if conflito is not None:
            raise serializers.ValidationError(
                {
                    "product_links": (
                        f'"{conflito.product.name}" já tem desconto na regra '
                        f'"{conflito.promotion.name}" desta mesma tabela. '
                        "Ajuste aquela regra ou use outra tabela."
                    )
                }
            )

    def _gravar_links(self, promotion, links):
        # Substitui o conjunto inteiro: a tela manda a lista final, e um merge
        # deixaria para trás produtos que o operador acabou de retirar — ainda
        # descontando.
        PromotionProduct.all_objects.filter(promotion_id=promotion.pk).delete()
        for link in links:
            PromotionProduct.objects.create(
                account_id=promotion.account_id,
                restaurant_id=promotion.restaurant_id,
                branch_id=promotion.branch_id,
                promotion=promotion,
                **link,
            )

    def create(self, validated_data):
        links = validated_data.pop("product_links", [])
        promotion = super().create(validated_data)
        self._gravar_links(promotion, links)
        return promotion

    def update(self, instance, validated_data):
        links = validated_data.pop("product_links", None)
        promotion = super().update(instance, validated_data)
        if links is not None:
            self._gravar_links(promotion, links)
        return promotion


class DiscountTableSerializer(TenantModelSerializer):
    """A tabela, com as regras dentro e o porquê do estado dela."""

    rules = PromotionSerializer(many=True, read_only=True)
    is_active = serializers.BooleanField(read_only=True)
    status_label = serializers.CharField(read_only=True)
    rule_count = serializers.SerializerMethodField()

    class Meta:
        model = DiscountTable
        fields = "__all__"
        read_only_fields = AUDIT_READ_ONLY_FIELDS

    def get_rule_count(self, obj):
        anotado = getattr(obj, "total_regras", None)
        if anotado is not None:
            return anotado
        return obj.rules.count()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        inicio = attrs.get("starts_at", getattr(self.instance, "starts_at", None))
        fim = attrs.get("ends_at", getattr(self.instance, "ends_at", None))
        if inicio and fim and fim <= inicio:
            raise serializers.ValidationError(
                {"ends_at": "O fim da tabela tem de ser depois do início."}
            )
        return attrs
