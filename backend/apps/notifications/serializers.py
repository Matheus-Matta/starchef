from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = [
            "id",
            "category",
            "level",
            "title",
            "body",
            "url",
            "entity",
            "object_id",
            "metadata",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields
