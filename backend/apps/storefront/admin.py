from django.contrib import admin
from unfold.admin import ModelAdmin

from apps.core.admin_mixins import TenantModelAdmin, TenantTabularInline
from apps.storefront.models import (
    MenuAsset,
    MenuDomain,
    MenuPage,
    MenuPageVersion,
    MenuSite,
    MenuTemplate,
)


class MenuPageInline(TenantTabularInline):
    model = MenuPage
    extra = 0
    fields = ("title", "slug", "is_home", "status", "display_order", "published_at")
    readonly_fields = ("status", "published_at")
    show_change_link = True


class MenuDomainInline(TenantTabularInline):
    model = MenuDomain
    extra = 0
    fields = ("hostname", "domain_type", "is_primary", "verified", "ssl_status")


@admin.register(MenuSite)
class MenuSiteAdmin(TenantModelAdmin):
    list_display = ("slug", "name", "account", "restaurant", "is_active", "published_at")
    list_filter = ("account", "is_active")
    search_fields = ("slug", "name", "restaurant__trade_name")
    inlines = [MenuPageInline, MenuDomainInline]


@admin.register(MenuPage)
class MenuPageAdmin(TenantModelAdmin):
    list_display = ("title", "slug", "site", "status", "is_home", "published_at")
    list_filter = ("account", "restaurant", "status", "is_home")
    search_fields = ("title", "slug", "site__slug")
    # O JSON do editor é grande e não se edita à mão — o /admin serve para
    # inspecionar, não para alterar a árvore de blocos.
    readonly_fields = ("draft_data", "published_data", "published_at", "published_by")


@admin.register(MenuPageVersion)
class MenuPageVersionAdmin(TenantModelAdmin):
    list_display = ("page", "number", "origin", "label", "created_by", "created_at")
    list_filter = ("account", "origin")
    search_fields = ("page__slug", "label")
    readonly_fields = ("data",)


@admin.register(MenuTemplate)
class MenuTemplateAdmin(ModelAdmin):
    """Catálogo da plataforma: não é dado de conta, então não usa o mixin tenant."""

    list_display = ("name", "slug", "category", "is_active", "sort_order", "updated_at")
    list_filter = ("is_active", "category")
    search_fields = ("name", "slug", "description")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(MenuAsset)
class MenuAssetAdmin(TenantModelAdmin):
    list_display = ("original_name", "account", "restaurant", "content_type", "size", "created_at")
    list_filter = ("account", "restaurant", "content_type")
    search_fields = ("original_name", "checksum")
    readonly_fields = ("size", "width", "height", "checksum", "content_type")


@admin.register(MenuDomain)
class MenuDomainAdmin(TenantModelAdmin):
    list_display = ("hostname", "site", "domain_type", "is_primary", "verified", "ssl_status")
    list_filter = ("account", "domain_type", "verified", "ssl_status")
    search_fields = ("hostname",)
    readonly_fields = ("verification_token", "verified_at")
