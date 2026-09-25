from django.db.models import Count, Prefetch
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.promotions.models import DiscountTable, Promotion
from apps.promotions.serializers import DiscountTableSerializer, PromotionSerializer


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

        Recebe a lista de ids na ordem desejada e grava a posição de cada uma, em
        UMA chamada: a posição é única por tabela, e salvar regra por regra
        colidiria no meio do caminho com duas disputando a posição 2.

        A LISTA TEM DE SER COMPLETA — todas as regras daquela tabela. Reordenar
        metade deixaria a outra metade ocupando posições do intervalo de destino,
        e o resultado seria um 409 cru no lugar de uma ordem nova.
        """
        ids = [str(item) for item in (request.data.get("ids") or [])]
        if not ids:
            return Response({"detail": "Informe a lista de ids na ordem desejada."}, status=400)
        regras = {str(r.pk): r for r in self.get_queryset().filter(pk__in=ids)}
        faltando = [i for i in ids if i not in regras]
        if faltando:
            return Response({"detail": "Regra desconhecida na lista de ordenação."}, status=400)
        tabelas = {r.table_id for r in regras.values()}
        if len(tabelas) > 1:
            return Response(
                {"detail": "Reordene uma tabela por vez: a prioridade só existe dentro da tabela."},
                status=400,
            )
        tabela_id = tabelas.pop()
        total_da_tabela = Promotion.objects.filter(table_id=tabela_id).count()
        if len(regras) != total_da_tabela:
            return Response(
                {
                    "detail": (
                        "Envie TODAS as regras da tabela na ordem desejada. "
                        f"A tabela tem {total_da_tabela} e a lista trouxe {len(regras)}."
                    )
                },
                status=400,
            )
        return Response(self._gravar_ordem(ids, regras, request.user))

    def _gravar_ordem(self, ids, regras, usuario):
        """Desloca as posições para fora do caminho, e depois as traz de volta.

        O deslocamento existe porque a posição é única: zerar todas antes de
        reatribuir violaria a unicidade na hora (três regras na posição 0), e
        atribuir direto colidiria com quem já está no lugar de destino. Somar um
        offset grande mantém as posições DISTINTAS entre si e livra o intervalo
        1..N de uma vez.
        """
        from django.db import transaction
        from django.db.models import F

        OFFSET = 100_000
        with transaction.atomic():
            Promotion.objects.filter(pk__in=regras.keys()).update(position=F("position") + OFFSET)
            for indice, identificador in enumerate(ids, start=1):
                regra = regras[identificador]
                regra.position = indice
                regra.updated_by = usuario
                regra.save(update_fields=["position", "updated_by", "updated_at"])
        atualizadas = self.get_queryset().filter(pk__in=regras.keys())
        return self.get_serializer(atualizadas, many=True).data

# As rotas de cupom vivem em `views_coupon.py`: são outro assunto, e o
# `config/urls.py` importa as duas metades pelo mesmo caminho de sempre.
from apps.promotions.views_coupon import (  # noqa: E402,F401
    CouponRedemptionViewSet,
    CouponViewSet,
    aplicar_cupom_no_pedido,
)
