from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.restaurants.models import Restaurant

from .models import KdsColumn, KdsStation
from .rule_schema import DEFAULT_STATION_RULES, FIELDS, OPERATORS
from .serializers import KdsColumnSerializer, KdsStationSerializer
from .station_templates import STATION_TEMPLATES, TEMPLATES_BY_KEY


class KdsStationViewSet(BaseTenantViewSet):
    serializer_class = KdsStationSerializer
    queryset = KdsStation.objects.prefetch_related("columns").all()
    filterset_fields = ["is_active"]

    @action(detail=False, methods=["get"], url_path="templates")
    def templates(self, request):
        return Response(STATION_TEMPLATES)

    @action(detail=False, methods=["get"], url_path="rule-options")
    def rule_options(self, request):
        return Response({
            "actions": ["include", "exclude", "move"],
            "fields": sorted(FIELDS),
            "operators": sorted(OPERATORS),
        })

    @action(detail=False, methods=["post"], url_path="from-template")
    def from_template(self, request):
        template = TEMPLATES_BY_KEY.get(request.data.get("template"))
        if template is None:
            return Response({"template": "Modelo inválido."}, status=status.HTTP_400_BAD_REQUEST)
        account = getattr(request, "account", None)
        if account is None:
            return Response({"detail": "Contexto de conta é obrigatório."}, status=status.HTTP_400_BAD_REQUEST)
        restaurant = Restaurant.objects.filter(pk=request.data.get("restaurant"), account=account).first()
        if restaurant is None:
            return Response({"restaurant": "Selecione um restaurante válido."}, status=status.HTTP_400_BAD_REQUEST)

        name = (request.data.get("name") or template["name"]).strip()
        try:
            sla_minutes = int(request.data.get("sla_minutes") or 15)
        except (TypeError, ValueError):
            sla_minutes = 15
        sectors = request.data.get("sectors")
        if not isinstance(sectors, list):
            sectors = template.get("sectors", [])
        with transaction.atomic():
            station = KdsStation.objects.create(
                account=account, restaurant=restaurant, name=name,
                sla_minutes=sla_minutes, sectors=sectors,
                rules=[dict(rule) for rule in DEFAULT_STATION_RULES],
            )
            KdsColumn.objects.bulk_create([
                KdsColumn(
                    account=account, station=station, position=position,
                    name=column["name"], color=column["color"],
                    is_entry=column["is_entry"], is_done=column["is_done"],
                )
                for position, column in enumerate(template["columns"])
            ])
        station = self.get_queryset().get(pk=station.pk)
        return Response(self.get_serializer(station).data, status=status.HTTP_201_CREATED)


class KdsColumnViewSet(BaseTenantViewSet):
    serializer_class = KdsColumnSerializer
    queryset = KdsColumn.objects.select_related("station").all()
    filterset_fields = ["station", "is_active"]
    ordering_fields = ["position", "name"]
    ordering = ["position"]
