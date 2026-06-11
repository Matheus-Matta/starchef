from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

from apps.accounts.views import (
    AccountViewSet,
    GlobalSystemConfigViewSet,
    LoginView,
    LogoutView,
    MeView,
    PlanViewSet,
    RoleViewSet,
    SubscriptionViewSet,
    UserViewSet,
)
from apps.customers.views import CustomerAddressViewSet, CustomerViewSet
from apps.invoices.views import InvoiceViewSet
from apps.kitchen.views import KitchenItemViewSet, KitchenOrderViewSet
from apps.menu.views import (
    IngredientViewSet,
    ProductAddonViewSet,
    ProductCategoryViewSet,
    ProductVariationViewSet,
    ProductViewSet,
)
from apps.orders.views import OrderItemViewSet, OrderViewSet
from apps.payments.views import CashRegisterViewSet, PaymentMethodViewSet, PaymentViewSet
from apps.printers.views import PrinterViewSet, PrintJobViewSet
from apps.reports.views import DashboardReportView, SalesReportView
from apps.restaurants.views import BranchViewSet, RestaurantViewSet, TableSectorViewSet, TableViewSet
from apps.stock.views import StockLocationViewSet, StockMovementViewSet


def healthcheck(_request):
    return JsonResponse({"status": "ok"})


router = DefaultRouter()
router.register("accounts", AccountViewSet, basename="accounts")
router.register("plans", PlanViewSet, basename="plans")
router.register("subscriptions", SubscriptionViewSet, basename="subscriptions")
router.register("system-config", GlobalSystemConfigViewSet, basename="system-config")
router.register("users", UserViewSet, basename="users")
router.register("roles", RoleViewSet, basename="roles")
router.register("restaurants", RestaurantViewSet, basename="restaurants")
router.register("branches", BranchViewSet, basename="branches")
router.register("tables/sectors", TableSectorViewSet, basename="table-sectors")
router.register("tables", TableViewSet, basename="tables")
router.register("customers/addresses", CustomerAddressViewSet, basename="customer-addresses")
router.register("customers", CustomerViewSet, basename="customers")
router.register("menu/categories", ProductCategoryViewSet, basename="product-categories")
router.register("menu/products", ProductViewSet, basename="products")
router.register("menu/addons", ProductAddonViewSet, basename="product-addons")
router.register("menu/variations", ProductVariationViewSet, basename="product-variations")
router.register("menu/ingredients", IngredientViewSet, basename="ingredients")
router.register("orders/items", OrderItemViewSet, basename="order-items")
router.register("orders", OrderViewSet, basename="orders")
router.register("kitchen/items", KitchenItemViewSet, basename="kitchen-items")
router.register("kitchen/orders", KitchenOrderViewSet, basename="kitchen-orders")
router.register("payments/methods", PaymentMethodViewSet, basename="payment-methods")
router.register("payments", PaymentViewSet, basename="payments")
router.register("cash-register", CashRegisterViewSet, basename="cash-register")
router.register("invoices", InvoiceViewSet, basename="invoices")
router.register("printers", PrinterViewSet, basename="printers")
router.register("print-jobs", PrintJobViewSet, basename="print-jobs")
router.register("stock/locations", StockLocationViewSet, basename="stock-locations")
router.register("stock/movements", StockMovementViewSet, basename="stock-movements")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", healthcheck, name="healthcheck"),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/schema/swagger-ui/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/v1/auth/login/", LoginView.as_view(), name="token_obtain_pair"),
    path("api/v1/auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/v1/auth/verify/", TokenVerifyView.as_view(), name="token_verify"),
    path("api/v1/auth/me/", MeView.as_view(), name="auth_me"),
    path("api/v1/auth/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/reports/sales/", SalesReportView.as_view(), name="sales-report"),
    path("api/v1/reports/dashboard/", DashboardReportView.as_view(), name="dashboard-report"),
    path("api/v1/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
