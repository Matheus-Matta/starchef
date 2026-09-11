from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.core.viewsets import BaseTenantViewSet
from apps.assets.models import Asset, AssetDisposal, AssetLocationHistory
from apps.assets.serializers import (
    AssetDisposalSerializer,
    AssetLocationHistorySerializer,
    AssetSerializer,
    ReusableAssetMovementSerializer,
    ReusableAssetSerializer,
)
from apps.menu.models import Product
from apps.stock.models import StockLocation, StockMovement


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

    @action(detail=False, methods=["post"], url_path="bulk-update-status")
    def bulk_update_status(self, request):
        """Atualiza o status operacional de múltiplos ativos em lote."""
        ids = request.data.get("ids", [])
        new_status = request.data.get("status")
        valid_statuses = [choice[0] for choice in Asset.STATUS_CHOICES]

        if not new_status or new_status not in valid_statuses:
            return Response(
                {"error": f"Status inválido. Escolha um dos seguintes: {', '.join(valid_statuses)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ids or not isinstance(ids, list):
            return Response(
                {"error": "Nenhum ativo selecionado para atualização."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        queryset = self.filter_queryset(self.get_queryset()).filter(id__in=ids)
        updated_count = queryset.update(status=new_status, updated_at=timezone.now())

        return Response({
            "success": True,
            "updated": updated_count,
            "status": new_status,
        })

    @action(detail=False, methods=["post"], url_path="bulk-transfer")
    def bulk_transfer(self, request):
        """Transfere múltiplos ativos para uma nova localização física em lote."""
        ids = request.data.get("ids", [])
        to_location_id = request.data.get("to_location")
        reason = request.data.get("reason", "Transferência em lote")
        notes = request.data.get("notes", "")

        if not to_location_id:
            return Response(
                {"error": "O campo 'to_location' é obrigatório."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not ids or not isinstance(ids, list):
            return Response(
                {"error": "Nenhum ativo selecionado para transferência."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        to_location = get_object_or_404(
            StockLocation.all_objects.filter(account=request.account),
            id=to_location_id,
        )

        assets = list(self.filter_queryset(self.get_queryset()).filter(id__in=ids))
        if not assets:
            return Response(
                {"error": "Nenhum ativo encontrado para os identificadores fornecidos."},
                status=status.HTTP_404_NOT_FOUND,
            )

        history_records = []
        asset_ids_to_update = []
        for asset in assets:
            history_records.append(
                AssetLocationHistory(
                    account=request.account,
                    restaurant=asset.restaurant,
                    branch=asset.branch,
                    asset=asset,
                    from_location=asset.location,
                    to_location=to_location,
                    moved_by=request.user,
                    reason=reason,
                    notes=notes,
                )
            )
            asset_ids_to_update.append(asset.id)

        with transaction.atomic():
            AssetLocationHistory.objects.bulk_create(history_records)
            Asset.objects.filter(id__in=asset_ids_to_update).update(
                location=to_location,
                updated_at=timezone.now(),
            )

        return Response({
            "success": True,
            "transferred": len(asset_ids_to_update),
            "to_location": {
                "id": str(to_location.id),
                "name": to_location.name,
            },
        })


class AssetLocationHistoryViewSet(BaseTenantViewSet):
    serializer_class = AssetLocationHistorySerializer
    queryset = AssetLocationHistory.objects.select_related("asset", "from_location", "to_location", "moved_by").all()
    filterset_fields = ["asset", "to_location"]
    ordering_fields = ["moved_at"]
    ordering = ["-moved_at"]


class ReusableAssetViewSet(BaseTenantViewSet):
    serializer_class = ReusableAssetSerializer
    queryset = Product.objects.none()
    search_fields = ["name", "internal_code", "brand", "model"]
    ordering_fields = ["name", "internal_code", "created_at"]
    ordering = ["name"]

    def get_queryset(self):
        account = getattr(self.request, "account", None)
        if account is None or not self.request.user.is_authenticated:
            return Product.all_objects.none()
        return (
            Product.all_objects
            .filter(account=account, item_type=Product.ITEM_REUSABLE, deleted_at__isnull=True)
            .distinct()
        )

    def perform_create(self, serializer):
        account = getattr(self.request, "account", None)
        profile = getattr(self.request.user, "profile", None)
        restaurant = getattr(profile, "restaurant", None)
        branch = getattr(profile, "branch", None)
        serializer.save(
            account=account,
            restaurant=restaurant,
            branch=branch,
            item_type=Product.ITEM_REUSABLE,
            tracking_mode=Product.TRACKING_QUANTITY,
            is_active=False,
            available_for_table=False,
            available_for_counter=False,
            available_for_delivery=False,
            controls_stock=True,
            created_by=self.request.user,
            updated_by=self.request.user,
        )

    @action(detail=True, methods=["post"], url_path="record-loss")
    def record_loss(self, request, pk=None):
        from decimal import Decimal
        product = self.get_object()
        raw_qty = request.data.get("quantity")
        if not raw_qty:
            return Response({"error": "Informe a quantidade."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            qty = Decimal(str(raw_qty))
            if qty <= 0:
                raise ValueError()
        except Exception:
            return Response({"error": "A quantidade deve ser um número positivo maior que zero."}, status=status.HTTP_400_BAD_REQUEST)

        movement_type = request.data.get("movement_type", StockMovement.TYPE_BREAKAGE)
        if movement_type not in [StockMovement.TYPE_BREAKAGE, StockMovement.TYPE_LOSS, StockMovement.TYPE_ASSET_DISPOSAL]:
            movement_type = StockMovement.TYPE_BREAKAGE

        location_id = request.data.get("location")
        location = None
        if location_id:
            location = StockLocation.all_objects.filter(account=request.account, id=location_id).first()
        if not location:
            last_move = StockMovement.all_objects.filter(product=product, location__isnull=False).order_by("-created_at").first()
            if last_move:
                location = last_move.location
            else:
                location = StockLocation.all_objects.filter(account=request.account, is_active=True).first()

        if not location:
            return Response({"error": "Nenhum local de estoque encontrado para registrar a perda."}, status=status.HTTP_400_BAD_REQUEST)

        notes = (request.data.get("notes") or "").strip()

        with transaction.atomic():
            movement = StockMovement.objects.create(
                account=request.account,
                restaurant=product.restaurant,
                branch=product.branch,
                product=product,
                location=location,
                operator=request.user,
                movement_type=movement_type,
                quantity=-abs(qty),
                stock_unit=(product.stock_unit or "UN").upper(),
                unit_cost=product.estimated_cost or Decimal("0.00"),
                total_cost=(product.estimated_cost or Decimal("0.00")) * qty,
                reason=notes or ("Quebra de vasilhame/material" if movement_type == StockMovement.TYPE_BREAKAGE else "Perda/extravio de vasilhame/material"),
            )

        serializer = self.get_serializer(product)
        return Response({
            "success": True,
            "message": f"Baixa de {qty} {product.stock_unit or 'UN'} registrada com sucesso!",
            "movement_id": str(movement.id),
            "item": serializer.data,
        })

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        product = self.get_object()
        moves = (
            StockMovement.all_objects
            .filter(product=product, deleted_at__isnull=True)
            .select_related("operator", "location", "nfe")
            .order_by("-created_at")
        )
        data = ReusableAssetMovementSerializer(moves, many=True).data
        return Response(data)

