from django.contrib import admin

from apps.notifications.models import Notification


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("title", "recipient", "category", "level", "is_read", "created_at")
    list_filter = ("category", "level", "is_read", "account")
    search_fields = ("title", "body", "recipient__username", "recipient__email")
    autocomplete_fields = ("recipient",)
    readonly_fields = ("created_at", "updated_at", "read_at")
