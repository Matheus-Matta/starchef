"""As rotas do cupom: cadastro, conferência e histórico de resgate.

Separadas das rotas de promoção porque o cupom tem um verbo que a promoção não
tem — CONFERIR. O caixa precisa saber se aquele código vale para AQUELE pedido
antes de cobrar, e essa pergunta não existe numa promoção de vitrine.
"""

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.promotions.models import Coupon, CouponRedemption
from apps.promotions.serializers import CouponRedemptionSerializer, CouponSerializer


class CouponViewSet(BaseTenantViewSet):
    """O cadastro dos cupons e a conferência que o caixa faz antes de cobrar."""

    serializer_class = CouponSerializer
    queryset = (
        Coupon.objects.annotate(total_resgates=Count("redemptions", distinct=True))
        .prefetch_related("customer_groups", "customers")
        .all()
    )
    filterset_fields = ["is_enabled", "discount_kind", "customer_groups"]
    search_fields = ["code", "name", "description"]
    # `total_resgates`: as sugestões do pagamento mostram os mais usados.
    ordering_fields = ["code", "created_at", "ends_at", "total_resgates"]

    def get_queryset(self):
        # A contagem entra AQUI: o mixin de tenant remonta a consulta a partir
        # do model e descarta o `annotate` declarado na classe — ordenar por
        # `total_resgates` dava 500 ("Cannot resolve keyword").
        consulta = super().get_queryset().annotate(
            total_resgates=Count("redemptions", distinct=True)
        )
        # `vigentes=1`: só o que o caixa pode aplicar agora — ligado e dentro do
        # prazo. Sugerir um vencido seria um toque para ouvir uma recusa.
        if self.request.query_params.get("vigentes") in ("1", "true"):
            agora = timezone.now()
            consulta = consulta.filter(is_enabled=True).filter(
                Q(starts_at__isnull=True) | Q(starts_at__lte=agora),
                Q(ends_at__isnull=True) | Q(ends_at__gte=agora),
            )
        return consulta

    @action(detail=False, methods=["post"], url_path="validate")
    def validate_code(self, request):
        """Confere um cupom contra um pedido SEM aplicá-lo.

        É o que o caixa chama enquanto o cliente está falando: devolve o motivo
        da recusa ou o valor do desconto, e não muda nada. Aplicar para depois
        desfazer deixaria rastro de cupom em pedido que o cliente desistiu de
        fechar — e queimaria o limite de um cupom de uso único.
        """
        from apps.orders.models import Order
        from apps.promotions.coupon_service import avaliar_no_pedido, buscar_cupom

        codigo = request.data.get("code") or ""
        pedido_id = request.data.get("order")
        if not pedido_id:
            return Response({"detail": "Informe o pedido a conferir."}, status=400)
        pedido = Order.objects.filter(pk=pedido_id).first()
        if pedido is None:
            return Response({"detail": "Pedido não encontrado."}, status=404)
        cupom = buscar_cupom(request.account.id, codigo)
        motivo, desconto, cliente = avaliar_no_pedido(cupom, pedido)
        return Response(
            {
                "valid": motivo is None,
                "reason": motivo,
                "coupon": CouponSerializer(cupom, context=self.get_serializer_context()).data,
                "discount": desconto,
                "customer": str(cliente.pk) if cliente is not None else None,
                "customer_name": cliente.name if cliente is not None else None,
            }
        )

    @action(detail=True, methods=["get"], url_path="redemptions")
    def redemptions(self, request, pk=None):
        """Quem usou este cupom. É a auditoria do "compra única por cliente"."""
        cupom = self.get_object()
        resgates = (
            CouponRedemption.objects.filter(coupon=cupom)
            .select_related("customer", "order")
            .order_by("-created_at")
        )
        pagina = self.paginate_queryset(resgates)
        serializer = CouponRedemptionSerializer(
            pagina if pagina is not None else resgates,
            many=True,
            context=self.get_serializer_context(),
        )
        if pagina is not None:
            return self.get_paginated_response(serializer.data)
        return Response(serializer.data)


class CouponRedemptionViewSet(BaseTenantViewSet):
    """Os resgates, só leitura — eles nascem do pagamento do pedido."""

    serializer_class = CouponRedemptionSerializer
    queryset = CouponRedemption.objects.select_related("coupon", "customer", "order").all()
    http_method_names = ["get", "head", "options"]
    filterset_fields = ["coupon", "customer"]
    search_fields = ["document", "coupon__code"]
    ordering_fields = ["created_at", "amount"]
