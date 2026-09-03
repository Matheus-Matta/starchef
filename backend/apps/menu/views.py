from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.core.access import is_tenant_admin
from apps.core.modules import MODULE_ECOMMERCE
from apps.core.viewsets import BaseTenantViewSet
from apps.menu.models import (
    Ingredient,
    Menu,
    MenuItem,
    Product,
    ProductAddon,
    ProductCategory,
    ProductUnitConversion,
    ProductVariation,
    Recipe,
    RecipeItem,
)
from apps.menu.serializers import (
    IngredientSerializer,
    MenuItemSerializer,
    MenuSerializer,
    ProductAddonSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    ProductUnitConversionSerializer,
    ProductVariationSerializer,
    PublicMenuSerializer,
    RecipeItemSerializer,
    RecipeSerializer,
)


class ProductCategoryViewSet(BaseTenantViewSet):
    serializer_class = ProductCategorySerializer
    queryset = ProductCategory.objects.select_related("restaurant", "branch", "parent").all()
    filterset_fields = ["parent", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["display_order", "name", "created_at"]
    ordering = ["display_order", "name"]


class ProductUnitConversionViewSet(BaseTenantViewSet):
    serializer_class = ProductUnitConversionSerializer
    queryset = ProductUnitConversion.objects.select_related("product").all()
    filterset_fields = ["product", "source_unit", "target_unit"]
    search_fields = ["product__name", "source_unit", "target_unit", "supplier_cnpj", "supplier_product_code"]
    ordering_fields = ["created_at"]


class ProductViewSet(BaseTenantViewSet):
    serializer_class = ProductSerializer
    queryset = Product.objects.select_related("restaurant", "branch", "category", "sector").prefetch_related("variations", "restaurants").all()
    filterset_fields = [
        "category",
        "product_type",
        "item_type",
        "tracking_mode",
        "controls_stock",
        "production_sector", "sector",
        "is_active",
        "available_for_table",
        "available_for_counter",
        "available_for_delivery",
    ]
    search_fields = ["name", "internal_code", "gtin", "brand", "model", "description"]
    ordering_fields = ["name", "sale_price", "created_at", "updated_at"]
    ordering = ["name"]

    def get_queryset(self):
        account = getattr(self.request, "account", None)
        if account is None or not self.request.user.is_authenticated:
            return Product.all_objects.none()
        queryset = (
            Product.all_objects
            .filter(account=account, deleted_at__isnull=True)
            .select_related("restaurant", "branch", "category", "sector")
            .prefetch_related("variations", "restaurants")
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
    queryset = ProductVariation.objects.select_related("restaurant", "branch", "product").all()
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
    queryset = Ingredient.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["unit", "is_active"]
    search_fields = ["name"]
    ordering_fields = ["name", "average_cost", "minimum_stock", "created_at"]
    ordering = ["name"]


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
    required_module = MODULE_ECOMMERCE  # cardapio digital
    serializer_class = MenuSerializer
    queryset = Menu.objects.select_related("restaurant", "branch").all()
    filterset_fields = ["channel", "is_active"]
    search_fields = ["name", "slug"]


class MenuItemViewSet(BaseTenantViewSet):
    required_module = MODULE_ECOMMERCE  # cardapio digital
    serializer_class = MenuItemSerializer
    queryset = MenuItem.objects.select_related("restaurant", "branch", "menu", "product").all()
    filterset_fields = ["menu", "product", "is_active"]
    ordering_fields = ["display_order"]


class PublicMenuView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    # Cardápio público: dezenas de clientes de um restaurante saem pelo mesmo IP
    # (WiFi/NAT), então o limite global `anon` (60/min) os bloquearia. Escopo
    # próprio, bem mais generoso.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_menu"

    def get(self, request, slug):
        try:
            menu = Menu.objects.prefetch_related(
                Prefetch(
                    "items",
                    queryset=MenuItem.objects.filter(is_active=True)
                    .select_related("product__category")
                    .prefetch_related("product__variations"),
                    to_attr="active_items",
                )
            ).get(slug=slug, is_active=True)
        except Menu.DoesNotExist:
            return Response({"detail": "Cardápio não encontrado."}, status=404)
        return Response(PublicMenuSerializer(menu).data)

