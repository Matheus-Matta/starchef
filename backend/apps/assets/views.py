from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.assets.models import Asset, AssetDisposal, AssetLocationHistory
from apps.assets.serializers import (
    AssetDisposalSerializer,
    AssetLocationHistorySerializer,
    AssetSerializer,
)
from apps.stock.models import StockLocation


class AssetViewSet(BaseTenantViewSet):
    serializer_class = AssetSerializer
    queryset = (
        Asset.objects
        .select_related("restaurant", "branch", "product", "location", "responsible_person", "nfe")
        .prefetch_related("location_history")
        .all()
    )
    filterset_fields = ["product", "location", "status", "responsible_person"]
    search_fields = [
        "asset_code",
        "serial_number",
        "patrimony_number",
        "product__name",
        "brand",
        "model",
        "supplier_name",
    ]
    ordering_fields = ["asset_code", "purchase_date", "warranty_end_date", "created_at"]
    ordering = ["asset_code"]

    @action(detail=True, methods=["post"], url_path="transfer")
    def transfer_location(self, request, pk=None):
        """Transfere o equipamento para uma nova localização física."""
        asset = self.get_object()
        to_location_id = request.data.get("to_location")
        reason = request.data.get("reason", "")
        notes = request.data.get("notes", "")

        if not to_location_id:
            return Response(
                {"error": "O campo 'to_location' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        to_location = get_object_or_404(
            StockLocation.all_objects.filter(account=request.account),
            id=to_location_id,
        )

        with transaction.atomic():
            old_location = asset.location
            asset.location = to_location
            asset.save(update_fields=["location", "updated_at"])

            AssetLocationHistory.objects.create(
                account=request.account,
                restaurant=asset.restaurant,
                branch=asset.branch,
                asset=asset,
                from_location=old_location,
                to_location=to_location,
                moved_by=request.user,
                reason=reason,
                notes=notes,
            )

        serializer = self.get_serializer(asset)
        return Response(serializer.data)

    @action(detail=True, methods=["post"], url_path="dispose")
    def dispose(self, request, pk=None):
        """Registra a baixa/descarte do ativo preservando o histórico."""
        asset = self.get_object()
        disposal_type = request.data.get("disposal_type", AssetDisposal.DISPOSAL_SCRAPPED)
        reason = request.data.get("reason", "")
        sale_value = request.data.get("sale_value")
        notes = request.data.get("notes", "")

        if not reason:
            return Response(
                {"error": "O motivo da baixa é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if hasattr(asset, "disposal") and asset.disposal:
            return Response(
                {"error": "Este ativo já possui registro de baixa patrimonial."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            asset.status = Asset.STATUS_DISPOSED
            asset.save(update_fields=["status", "updated_at"])

            AssetDisposal.objects.create(
                account=request.account,
                restaurant=asset.restaurant,
                branch=asset.branch,
                asset=asset,
                disposal_type=disposal_type,
                sale_value=sale_value,
                authorized_by=request.user,
                reason=reason,
                notes=notes,
            )

        serializer = self.get_serializer(asset)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="qr/(?P<token>[^/.]+)")
    def lookup_qr(self, request, token=None):
        """Consulta equipamento pelo token do QR Code."""
        asset = get_object_or_404(
            Asset.all_objects.filter(account=request.account),
            qr_code_token=token,
        )
        serializer = self.get_serializer(asset)
        return Response(serializer.data)


class AssetLocationHistoryViewSet(BaseTenantViewSet):
    serializer_class = AssetLocationHistorySerializer
    queryset = AssetLocationHistory.objects.select_related("asset", "from_location", "to_location", "moved_by").all()
    filterset_fields = ["asset", "to_location"]
    ordering_fields = ["moved_at"]
    ordering = ["-moved_at"]
