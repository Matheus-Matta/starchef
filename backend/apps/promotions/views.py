from decimal import Decimal

from django.db.models import Count, Prefetch
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.api_errors import CouponRejected
from apps.core.viewsets import BaseTenantViewSet
from apps.promotions.models import Coupon, CouponRedemption, DiscountTable, Promotion
from apps.promotions.serializers import (
    CouponRedemptionSerializer,
    CouponSerializer,
    DiscountTableSerializer,
    PromotionSerializer,
)


class DiscountTableViewSet(BaseTenantViewSet):
    """As tabelas de desconto, com as regras dentro."""

    serializer_class = DiscountTableSerializer
    queryset = (
        DiscountTable.objects.annotate(total_regras=Count("rules", distinct=True))
        .prefetch_related(
            # As regras vêm na MESMA consulta, com os vínculos de produto: sem
            # isto, abrir uma tabela de dez regras custaria vinte idas ao banco.
            Prefetch("rules", queryset=Promotion.objects.prefetch_related("product_links__product")),
        )
        .all()
    )
    filterset_fields = ["is_enabled"]
    search_fields = ["name", "description"]
    ordering_fields = ["name", "created_at", "starts_at", "ends_at"]

    @action(detail=True, methods=["post"], url_path="toggle")
    def toggle(self, request, pk=None):
        """Liga ou desliga a tabela inteira, sem abrir o formulário.

        Existe porque desligar promoção é urgente por natureza: o preço saiu
        errado e está na tela do caixa AGORA. Obrigar a abrir o cadastro, achar
        o campo e salvar é tempo em que o erro continua vendendo.
        """
        tabela = self.get_object()
        tabela.is_enabled = not tabela.is_enabled
        tabela.updated_by = request.user
        tabela.save(update_fields=["is_enabled", "updated_by", "updated_at"])
        return Response(self.get_serializer(tabela).data)


class PromotionViewSet(BaseTenantViewSet):
    """As regras, avulsas — para reordenar e editar sem abrir a tabela."""

    serializer_class = PromotionSerializer
    queryset = (
        Promotion.objects.select_related("table")
        .prefetch_related("product_links__product", "categories", "sectors")
        .all()
    )
    filterset_fields = ["table", "is_enabled", "target_type", "discount_kind"]
    search_fields = ["name"]
    ordering_fields = ["position", "created_at"]

    @action(detail=False, methods=["post"], url_path="reorder")
    def reorder(self, request):
        """Reordena as regras de uma tabela. A ordem É a prioridade.

        Recebe a lista de ids na ordem desejada e grava a posição de cada uma.
        Vem em UMA chamada porque posição é única por tabela: salvar uma a uma
        colidiria no meio do caminho, com duas regras disputando a posição 2.
        """
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"detail": "Informe a lista de ids na ordem desejada."}, status=400)
        regras = {str(r.pk): r for r in self.get_queryset().filter(pk__in=ids)}
        # As posições saem todas do caminho antes de voltarem: sem isso, mover a
        # regra 3 para o topo colidiria com a que já está em 1.
        Promotion.objects.filter(pk__in=regras.keys()).update(position=0)
        for indice, identificador in enumerate(ids, start=1):
            regra = regras.get(str(identificador))
            if regra is None:
                continue
            regra.position = indice
            regra.updated_by = request.user
            regra.save(update_fields=["position", "updated_by", "updated_at"])
        return Response(self.get_serializer(self.get_queryset().filter(pk__in=regras.keys()), many=True).data)


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
    ordering_fields = ["code", "created_at", "ends_at"]

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


def aplicar_cupom_no_pedido(request, order):
    """Aplica o cupom do corpo da requisição a um pedido. Usado por `orders`.

    Vive aqui, e não em `orders/views.py`, para a regra do cupom ter um só
    dono: o pedido pede, as promoções decidem.
    """
    from apps.promotions.coupon_service import aplicar_cupom, retirar_cupom

    codigo = request.data.get("code")
    if codigo is None:
        raise CouponRejected("Informe o código do cupom.")
    if not str(codigo).strip():
        retirar_cupom(order)
        return None, Decimal("0.00")
    return aplicar_cupom(order, codigo)
