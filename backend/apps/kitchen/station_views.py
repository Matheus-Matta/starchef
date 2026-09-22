from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.restaurants.models import Restaurant
from apps.sla.models import ServiceLevelAgreement

from .models import KdsColumn, KdsStation
from .rule_schema import FIELDS, OPERATORS, validate_station_rules
from .serializers import KdsColumnSerializer, KdsStationSerializer
from .station_templates import STATION_TEMPLATES, TEMPLATES_BY_KEY
from .template_rules import template_rules


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
            sla_minutes = int(request.data.get("sla_minutes", 15))
        except (TypeError, ValueError):
            sla_minutes = 15
        if sla_minutes < 1:
            return Response({"sla_minutes": "Informe pelo menos 1 minuto."}, status=status.HTTP_400_BAD_REQUEST)
        sectors = request.data.get("sectors")
        if not isinstance(sectors, list):
            sectors = template.get("sectors", [])
        with transaction.atomic():
            station = KdsStation.objects.create(
                account=account, restaurant=restaurant, name=name,
                sla_minutes=sla_minutes, sectors=sectors,
            )
            # bulk_create não dispara post_save: as colunas precisam sincronizar.
            columns = [
                KdsColumn.objects.create(
                    account=account, station=station, position=position,
                    name=column["name"], color=column["color"],
                    is_entry=column["is_entry"], is_done=column["is_done"],
                )
                for position, column in enumerate(template["columns"])
            ]
            station.rules = validate_station_rules(template_rules(columns), station)
            station.save(update_fields=["rules", "updated_at"])
            # O quadro só exibe urgência se houver um SLA ativo vinculado.
            sla = ServiceLevelAgreement.objects.create(
                account=account, name=f"Preparo · {name}",
                sla_type=ServiceLevelAgreement.TYPE_PREP,
                target_minutes=sla_minutes, alert_minutes=max(1, (sla_minutes * 2) // 3),
            )
            sla.stations.add(station)
        station = self.get_queryset().get(pk=station.pk)
        return Response(self.get_serializer(station).data, status=status.HTTP_201_CREATED)


class KdsColumnViewSet(BaseTenantViewSet):
    serializer_class = KdsColumnSerializer
    queryset = KdsColumn.objects.select_related("station").all()
    filterset_fields = ["station", "is_active"]
    ordering_fields = ["position", "name"]
    ordering = ["position"]
