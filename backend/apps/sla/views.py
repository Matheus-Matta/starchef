from apps.core.viewsets import BaseTenantViewSet
from apps.sla.models import ServiceLevelAgreement
from apps.sla.serializers import ServiceLevelAgreementSerializer


class ServiceLevelAgreementViewSet(BaseTenantViewSet):
    serializer_class = ServiceLevelAgreementSerializer
    queryset = ServiceLevelAgreement.objects.prefetch_related(
        "restaurants",
        "stations",
        "columns__station",
    ).all()
    filterset_fields = ["sla_type", "priority", "is_active", "restaurants"]
    search_fields = ["name"]
    ordering_fields = ["name", "target_minutes", "priority", "created_at"]
    ordering = ["name"]
