from django.utils import timezone
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.notifications.models import Notification
from apps.notifications.serializers import NotificationSerializer


class NotificationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Notificações do usuário autenticado (somente as próprias).

    Lista paginada (padrão do projeto: `page_size` — o front pede 10 por vez com
    "carregar mais") + ações de leitura e contagem de não lidas.
    """

    serializer_class = NotificationSerializer
    filterset_fields = ["is_read", "category", "level"]

    def get_queryset(self):
        return (
            Notification.all_objects
            .filter(recipient=self.request.user, deleted_at__isnull=True)
            .order_by("-created_at")
        )

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({"unread": count})

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.mark_read()
        return Response(self.get_serializer(notification).data)

    @action(detail=False, methods=["post"], url_path="mark-all-read")
    def mark_all_read(self, request):
        updated = self.get_queryset().filter(is_read=False).update(is_read=True, read_at=timezone.now())
        return Response({"updated": updated})
