from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.access import is_tenant_admin
from apps.core.audit import record_audit
from apps.core.models import AuditLog
from apps.core.modules import MODULE_ECOMMERCE
from apps.core.viewsets import BaseTenantViewSet
from apps.menu.models import Ingredient, Menu, MenuItem, Product, ProductAddon, ProductCategory, ProductVariation, Recipe, RecipeItem
from apps.menu.serializers import (
    IngredientSerializer,
    MenuItemSerializer,
    MenuResolvedSerializer,
    MenuSerializer,
    ProductAddonSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    ProductVariationSerializer,
    RecipeItemSerializer,
    RecipeSerializer,
)


class ProductCategoryViewSet(BaseTenantViewSet):
    serializer_class = ProductCategorySerializer
    queryset = ProductCategory.objects.select_related("restaurant", "branch", "parent", "logo_image").all()
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["display_order", "name", "created_at"]
    ordering = ["display_order", "name"]


class ProductViewSet(BaseTenantViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related(
        "restaurant", "branch", "category", "sector", "logo_image"
    ).prefetch_related("variations__logo_image", "restaurants", "product_images__image").all()
    filterset_fields = [
        "category",
        "product_type",
        "production_sector", "sector",
        "is_active",
        "available_for_table",
        "available_for_counter",
        "available_for_delivery",
    ]
    search_fields = ["name", "internal_code", "description", "ean"]
    ordering_fields = ["name", "sale_price", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        account = getattr(self.request, "account", None)
        if account is None or not self.request.user.is_authenticated:
            return Product.all_objects.none()
        queryset = self.soft_delete_scope(
            Product.all_objects
            .filter(account=account)
            .select_related("restaurant", "branch", "category", "sector", "logo_image")
            .prefetch_related("variations__logo_image", "restaurants", "product_images__image")
        )
        profile = getattr(self.request.user, "profile", None)
        restaurant_id = self.request.query_params.get("restaurant")
        if not is_tenant_admin(self.request.user):
            restaurant_id = getattr(profile, "restaurant_id", None)
            if not restaurant_id:
                return queryset.none()
        if restaurant_id:
            queryset = queryset.filter(restaurants__id=restaurant_id)
        return queryset.distinct()

    def perform_create(self, serializer):
        selected = serializer.validated_data.get("restaurants") or []
        if not serializer.validated_data.get("restaurant") and selected:
            serializer.validated_data["restaurant"] = selected[0]
        super().perform_create(serializer)
        if not selected:
            serializer.instance.restaurants.add(serializer.instance.restaurant)

    def _get_addon(self, request):
        # Escopo por tenant: só adicionais da conta (queryset padrão do model).
        return get_object_or_404(ProductAddon, pk=request.data.get("addon"))

    @action(detail=True, methods=["post"], url_path="link-addon")
    def link_addon(self, request, pk=None):
        """Vincula um adicional a este produto (gerenciado na edição do produto)."""
        product = self.get_object()
        addon = self._get_addon(request)
        addon.products.add(product)
        return Response(
            {"id": addon.id, "name": addon.name, "price": addon.price, "is_active": addon.is_active},
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="unlink-addon")
    def unlink_addon(self, request, pk=None):
        """Desvincula um adicional deste produto."""
        product = self.get_object()
        addon = self._get_addon(request)
        addon.products.remove(product)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ProductAddonViewSet(BaseTenantViewSet):
    serializer_class = ProductAddonSerializer
    queryset = ProductAddon.objects.select_related("restaurant", "branch").prefetch_related("products").all()
    filterset_fields = ["production_sector", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "price", "created_at"]
    ordering = ["name"]


class ProductVariationViewSet(BaseTenantViewSet):
    serializer_class = ProductVariationSerializer
    queryset = ProductVariation.objects.select_related(
        "restaurant", "branch", "product", "product__logo_image", "logo_image"
    ).all()
    filterset_fields = ["product", "is_active"]
    search_fields = ["name", "product__name"]

    def perform_create(self, serializer):
        # A variação herda restaurante/filial do produto vinculado — assim não
        # depende do escopo selecionado no topo (evita "restaurante obrigatório").
        product = serializer.validated_data.get("product")
        if product is not None:
            serializer.validated_data.setdefault("restaurant", product.restaurant)
            if product.branch_id:
                serializer.validated_data.setdefault("branch", product.branch)
        super().perform_create(serializer)


class IngredientViewSet(BaseTenantViewSet):
    serializer_class = IngredientSerializer
    queryset = Ingredient.objects.select_related("restaurant", "branch", "supplier").all()
    filterset_fields = ["unit", "supplier", "is_active"]
    search_fields = ["name", "supplier__name"]
    ordering_fields = ["name", "average_cost", "minimum_stock", "created_at"]
    ordering = ["name"]

    @action(detail=False, methods=["post"], url_path="bulk")
    def bulk_create(self, request):
        """Cria varios insumos em uma unica transacao."""

        rows = request.data.get("items") if isinstance(request.data, dict) else None
        if not isinstance(rows, list) or not rows:
            return Response({"items": "Informe ao menos um insumo."}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > 100:
            return Response(
                {"items": "Cadastre no maximo 100 insumos por lote."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = self.get_serializer(data=rows, many=True)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            ingredients = serializer.save(
                account=request.account,
                created_by=request.user,
                updated_by=request.user,
            )
            for ingredient in ingredients:
                record_audit(
                    action=AuditLog.ACTION_CREATED,
                    instance=ingredient,
                    actor=request.user,
                    request=request,
                    metadata={"bulk_create": True},
                )
        return Response(self.get_serializer(ingredients, many=True).data, status=status.HTTP_201_CREATED)


class RecipeViewSet(BaseTenantViewSet):
    serializer_class = RecipeSerializer
    queryset = Recipe.objects.select_related("restaurant", "branch", "product").prefetch_related("items__ingredient").all()
    filterset_fields = ["product", "is_active", "auto_deduct_stock"]
    search_fields = ["product__name"]

    def perform_update(self, serializer):
        # Passa pela injeção de tenant/auditoria da base antes de recalcular.
        super().perform_update(serializer)
        from apps.menu.services import recalculate_recipe_costs
        recalculate_recipe_costs(serializer.instance)


class RecipeItemViewSet(BaseTenantViewSet):
    serializer_class = RecipeItemSerializer
    queryset = RecipeItem.objects.select_related("restaurant", "branch", "recipe__product", "ingredient").all()
    filterset_fields = ["recipe", "ingredient"]

    def _recalc(self, recipe):
        from apps.menu.services import recalculate_recipe_costs
        recalculate_recipe_costs(recipe)

    def perform_create(self, serializer):
        # Herda restaurante/filial da receita (que pertence a um produto/restaurante),
        # para não depender do escopo selecionado. super() injeta account/auditoria.
        recipe = serializer.validated_data.get("recipe")
        if recipe is not None:
            serializer.validated_data.setdefault("restaurant", recipe.restaurant)
            if recipe.branch_id:
                serializer.validated_data.setdefault("branch", recipe.branch)
        super().perform_create(serializer)
        self._recalc(serializer.instance.recipe)

    def perform_update(self, serializer):
        super().perform_update(serializer)
        self._recalc(serializer.instance.recipe)

    def perform_destroy(self, instance):
        recipe = instance.recipe
        instance.delete()
        self._recalc(recipe)


class MenuViewSet(BaseTenantViewSet):
    """Menus no estilo Shopify: listas nomeadas que os blocos do site consomem.

    Serve a navegacao do cabecalho, o carrossel de banners, a vitrine de
    categorias/produtos e a curadoria de catalogo — o `menu_type` diz para que
    aquele menu foi feito, e `source` diz se os itens sao escolhidos a mao ou
    respondidos por consulta (todas as categorias, mais vendidos...).
    """

    required_module = MODULE_ECOMMERCE
    serializer_class = MenuSerializer
    queryset = (
        Menu.objects.select_related("restaurant", "branch", "source_category")
        .prefetch_related("items__product", "items__category", "items__children")
        .all()
    )
    filterset_fields = ["channel", "is_active", "menu_type", "source"]
    search_fields = ["name", "slug"]
    ordering_fields = ["name", "menu_type", "created_at"]

    @action(detail=True, methods=["get"], url_path="resolved")
    def resolved(self, request, pk=None):
        """O menu como o SITE o recebe, com as origens dinamicas ja resolvidas.

        E o unico jeito de conferir um menu "mais vendidos" antes de publicar:
        ele nao tem item cadastrado para olhar no formulario.
        """
        menu = self.get_object()
        return Response(MenuResolvedSerializer(menu, context=self.get_serializer_context()).data)


class MenuItemViewSet(BaseTenantViewSet):
    """Entradas de um menu (produto, categoria, imagem ou link proprio)."""

    required_module = MODULE_ECOMMERCE
    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.select_related(
        "restaurant", "branch", "menu", "product", "category", "parent"
    ).all()
    filterset_fields = ["menu", "product", "category", "item_type", "parent", "is_active"]
    search_fields = ["title", "url"]
    ordering_fields = ["display_order", "created_at"]

    def perform_create(self, serializer):
        # Herda restaurante/filial do MENU: o item nao existe fora dele, e
        # depender do escopo selecionado no topo faria o cadastro falhar com
        # "restaurante obrigatorio" para quem esta com "todos" selecionado.
        menu = serializer.validated_data.get("menu")
        if menu is not None:
            serializer.validated_data.setdefault("restaurant", menu.restaurant)
            if menu.branch_id:
                serializer.validated_data.setdefault("branch", menu.branch)
        super().perform_create(serializer)
