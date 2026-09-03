from django.contrib import admin
from apps.assets.models import Asset, AssetDisposal, AssetLocationHistory


@admin.register(Asset)
class AssetAdmin(admin.ModelAdmin):
    list_display = ["asset_code", "product", "status", "location", "serial_number", "warranty_end_date"]
    search_fields = ["asset_code", "serial_number", "product__name", "brand", "model"]
    list_filter = ["status", "location"]


@admin.register(AssetLocationHistory)
class AssetLocationHistoryAdmin(admin.ModelAdmin):
    list_display = ["asset", "from_location", "to_location", "moved_at", "moved_by"]
    search_fields = ["asset__asset_code", "reason"]


@admin.register(AssetDisposal)
class AssetDisposalAdmin(admin.ModelAdmin):
    list_display = ["asset", "disposal_type", "disposed_at", "authorized_by"]
    search_fields = ["asset__asset_code", "reason"]
