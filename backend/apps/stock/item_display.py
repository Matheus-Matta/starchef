from rest_framework import serializers


class StockItemDisplaySerializer(serializers.Serializer):
    """Nome, unidade e codigo tanto para Product quanto para Ingredient."""

    ingredient_name = serializers.SerializerMethodField()
    ingredient_unit = serializers.SerializerMethodField()
    item_code = serializers.SerializerMethodField()

    def get_ingredient_name(self, obj):
        item = obj.product or obj.ingredient
        return item.name if item else ""

    def get_ingredient_unit(self, obj):
        return obj.product.stock_unit if obj.product else (obj.ingredient.unit if obj.ingredient else "")

    def get_item_code(self, obj):
        return obj.product.internal_code if obj.product else ""
