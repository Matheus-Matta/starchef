from django.contrib import admin

from apps.core.admin_mixins import TenantModelAdmin
from apps.customers.models import Customer, CustomerAddress


@admin.register(Customer)
class CustomerAdmin(TenantModelAdmin):
    list_display = ("name", "account", "phone", "email", "branch", "is_active")
    list_filter = ("account", "restaurant", "branch", "is_active")
    search_fields = ("name", "phone", "email", "document")


@admin.register(CustomerAddress)
class CustomerAddressAdmin(TenantModelAdmin):
    list_display = ("customer", "account", "label", "district", "city", "state", "is_default")
    list_filter = ("account", "restaurant", "branch", "city", "state")
