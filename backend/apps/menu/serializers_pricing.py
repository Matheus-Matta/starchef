"""A leitura da promoção no serializer do produto, resolvida uma vez por página.

Separado porque é onde vive a otimização que essa leitura exige: sem ela, uma
página de trinta produtos faria trinta vezes a mesma consulta às tabelas de
desconto — e o PDV carrega o cardápio inteiro na abertura do caixa.

Os CAMPOS continuam declarados no serializer: o DRF só coleta declaração de campo
de bases que já são serializer, e um mixin comum passaria batido em silêncio —
com o produto saindo sem preço e ninguém sabendo por quê.
"""

from rest_framework import serializers

from apps.menu.models import Product


class ProductPromotionReading:
    def get_promotion(self, obj):
        """De onde veio o desconto — para a tela poder dizer o motivo.

        Sem isto a grade mostraria um preço menor do que o cadastrado e ninguém
        saberia por quê: o gerente abriria o produto, veria o cadastro intacto e
        concluiria que o sistema está errado.
        """
        oferta = obj.active_promotion
        if oferta is None:
            return None
        return {
            "id": oferta.promotion_id,
            "name": oferta.promotion_name,
            "table": oferta.table_id,
            "table_name": oferta.table_name,
            "price": oferta.price,
            "compare_at_price": oferta.compare_at,
            "discount_amount": oferta.discount_amount,
            "discount_percent": oferta.discount_percent,
        }

    def to_representation(self, instance):
        self._resolver_promocoes_do_lote()
        return super().to_representation(instance)

    def _resolver_promocoes_do_lote(self):
        """Resolve a disputa de promoção da PÁGINA INTEIRA, uma vez.

        Cada produto sozinho custaria uma consulta às tabelas de desconto; o PDV
        carrega o cardápio inteiro na abertura do caixa, e trinta produtos por
        página viravam trinta consultas idênticas.
        """
        if getattr(self, "_lote_resolvido", False):
            return
        self._lote_resolvido = True
        pai = self.parent if isinstance(self.parent, serializers.ListSerializer) else None
        alvo = pai.instance if pai is not None else self.instance
        if alvo is None:
            return
        produtos = list(alvo) if not isinstance(alvo, Product) else [alvo]
        if not produtos:
            return
        from apps.promotions.pricing import primar

        # O restaurante vem do PERFIL de quem pediu: tabela de desconto presa a
        # uma loja nao pode descontar na outra. Sem perfil (admin da conta), a
        # conta inteira responde.
        perfil = getattr(getattr(self.context.get("request"), "user", None), "profile", None)
        primar(produtos, restaurant_id=getattr(perfil, "restaurant_id", None))
