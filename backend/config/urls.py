from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenVerifyView

from apps.accounts.views import (
    AccountViewSet,
    CookieTokenRefreshView,
    GlobalSystemConfigViewSet,
    LoginView,
    LogoutView,
    MeView,
    PlanViewSet,
    PermissionViewSet,
    RoleViewSet,
    SubscriptionViewSet,
    UserViewSet,
)
from apps.customers.views import CustomerAddressViewSet, CustomerViewSet
from apps.invoices.views import FiscalConfigViewSet, FiscalProfileViewSet, InvoiceViewSet
from apps.kitchen.views import KdsColumnViewSet, KdsStationViewSet, KitchenItemViewSet, KitchenOrderViewSet
from apps.sla.views import ServiceLevelAgreementViewSet
from apps.menu.views import (
    IngredientViewSet,
    MenuItemViewSet,
    MenuViewSet,
    ProductAddonViewSet,
    ProductCategoryViewSet,
    ProductVariationViewSet,
    ProductViewSet,
    PublicMenuView,
    RecipeItemViewSet,
    RecipeViewSet,
)
from apps.notifications.views import NotificationViewSet
from apps.orders.views import OrderItemViewSet, OrderViewSet
from apps.payments.views import CashRegisterViewSet, CashStationViewSet, PaymentMethodViewSet, PaymentViewSet
from apps.printers.views import PrinterViewSet, PrintJobViewSet, ScaleReadingViewSet, ScaleViewSet
from apps.reports.views import DashboardReportView, SalesReportView
from apps.restaurants.views import (
    BranchViewSet,
    CommandViewSet,
    DeliverymanViewSet,
    DeliveryZoneViewSet,
    RestaurantViewSet,
    TableSectorViewSet,
    TableViewSet,
)
from apps.stock.views import StockAlertView, StockLocationViewSet, StockMovementViewSet


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


def api_index(_request):
    return JsonResponse(
        {
            "name": "StarChef API",
            "health": "/health/",
            "swagger": "/api/schema/swagger-ui/",
            "login": "/api/v1/auth/login/",
        }
    )


router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="accounts")
router.register("plans", PlanViewSet, basename="plans")
router.register("subscriptions", SubscriptionViewSet, basename="subscriptions")
router.register("system-config", GlobalSystemConfigViewSet, basename="system-config")
router.register("users", UserViewSet, basename="users")
router.register("roles", RoleViewSet, basename="roles")
router.register("permissions", PermissionViewSet, basename="permissions")
router.register("restaurants", RestaurantViewSet, basename="restaurants")
router.register("branches", BranchViewSet, basename="branches")
router.register("tables/sectors", TableSectorViewSet, basename="table-sectors")
router.register("tables", TableViewSet, basename="tables")
router.register("commands", CommandViewSet, basename="commands")
router.register("delivery/zones", DeliveryZoneViewSet, basename="delivery-zones")
router.register("delivery/deliverymen", DeliverymanViewSet, basename="deliverymen")
router.register("customers/addresses", CustomerAddressViewSet, basename="customer-addresses")
router.register("customers", CustomerViewSet, basename="customers")
router.register("menu/categories", ProductCategoryViewSet, basename="product-categories")
router.register("menu/products", ProductViewSet, basename="products")
router.register("menu/addons", ProductAddonViewSet, basename="product-addons")
router.register("menu/variations", ProductVariationViewSet, basename="product-variations")
router.register("menu/ingredients", IngredientViewSet, basename="ingredients")
router.register("menu/recipes", RecipeViewSet, basename="recipes")
router.register("menu/recipe-items", RecipeItemViewSet, basename="recipe-items")
router.register("menu/menus", MenuViewSet, basename="menus")
router.register("menu/menu-items", MenuItemViewSet, basename="menu-items")
router.register("orders/items", OrderItemViewSet, basename="order-items")
router.register("orders", OrderViewSet, basename="orders")
router.register("sla", ServiceLevelAgreementViewSet, basename="sla")
router.register("kitchen/stations", KdsStationViewSet, basename="kds-stations")
router.register("kitchen/columns", KdsColumnViewSet, basename="kds-columns")
router.register("kitchen/items", KitchenItemViewSet, basename="kitchen-items")
router.register("kitchen/orders", KitchenOrderViewSet, basename="kitchen-orders")
router.register("payments/methods", PaymentMethodViewSet, basename="payment-methods")
router.register("payments", PaymentViewSet, basename="payments")
router.register("cash-register", CashRegisterViewSet, basename="cash-register")
router.register("cash-stations", CashStationViewSet, basename="cash-stations")
router.register("fiscal/config", FiscalConfigViewSet, basename="fiscal-config")
router.register("fiscal/profiles", FiscalProfileViewSet, basename="fiscal-profiles")
router.register("invoices", InvoiceViewSet, basename="invoices")
router.register("printers", PrinterViewSet, basename="printers")
router.register("print-jobs", PrintJobViewSet, basename="print-jobs")
router.register("scales/readings", ScaleReadingViewSet, basename="scale-readings")
router.register("scales", ScaleViewSet, basename="scales")
router.register("stock/locations", StockLocationViewSet, basename="stock-locations")
router.register("stock/movements", StockMovementViewSet, basename="stock-movements")
router.register("notifications", NotificationViewSet, basename="notifications")

urlpatterns = [
    path("", api_index, name="api-index"),
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", CookieTokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth_me"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/reports/sales/", SalesReportView.as_view(), name="sales-report"),
    path("api/v1/reports/dashboard/", DashboardReportView.as_view(), name="dashboard-report"),
    path("api/v1/stock/alerts/", StockAlertView.as_view(), name="stock-alerts"),
    path("api/v1/public/menu/<slug:slug>/", PublicMenuView.as_view(), name="public-menu"),
    path("api/v1/", include(router.urls)),
]

if settings.DEBUG:
    # Em dev o Django serve estáticos e media diretamente.
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
else:
    # Em produção:
    #  - estáticos são servidos pelo WhiteNoise (middleware, hasheados/comprimidos);
    #  - media (uploads dinâmicos) é servida pelo nginx (`location /media/`). O
    #    WhiteNoise NÃO serve media, pois indexa arquivos só no boot e uploads
    #    posteriores não apareceriam. Este re_path é um fallback para quando o app
    #    roda sem nginx na frente (o nginx intercepta /media/ antes de chegar aqui).
    from django.urls import re_path
    from django.views.static import serve as media_serve

    media_prefix = settings.MEDIA_URL.lstrip("/")
    urlpatterns += [
        re_path(
            rf"^{media_prefix}(?P<path>.*)$",
            media_serve,
            {"document_root": settings.MEDIA_ROOT},
        ),
    ]
