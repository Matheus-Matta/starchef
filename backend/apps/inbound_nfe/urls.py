from rest_framework.routers import SimpleRouter
from apps.inbound_nfe.views import (
    InboundNFeViewSet,
    InboundNFeItemViewSet,
    DFeDistributionDocumentViewSet,
)

# Este router e incluido pelo router principal, que ja e um DefaultRouter.
# Usar dois DefaultRouter registra duas vezes o conversor de sufixo do DRF e
# vira erro no Django 5.1 quando depreciacoes sao tratadas como falha.
router = SimpleRouter()
router.register(r"inbound-nfe", InboundNFeViewSet, basename="inbound-nfe")
router.register(r"inbound-nfe-items", InboundNFeItemViewSet, basename="inbound-nfe-items")
router.register(r"inbound-nfe-documents", DFeDistributionDocumentViewSet, basename="inbound-nfe-documents")

urlpatterns = router.urls
