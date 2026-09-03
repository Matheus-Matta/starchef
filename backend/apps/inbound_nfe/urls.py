from rest_framework.routers import DefaultRouter
from apps.inbound_nfe.views import (
    InboundNFeViewSet,
    InboundNFeItemViewSet,
    DFeDistributionDocumentViewSet,
)

router = DefaultRouter()
router.register(r"inbound-nfe", InboundNFeViewSet, basename="inbound-nfe")
router.register(r"inbound-nfe-items", InboundNFeItemViewSet, basename="inbound-nfe-items")
router.register(r"inbound-nfe-documents", DFeDistributionDocumentViewSet, basename="inbound-nfe-documents")

urlpatterns = router.urls
