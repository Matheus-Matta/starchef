"""Rota WSS do nó da NUVEM. A loja nunca precisa expor esta rota."""
from django.urls import path

from apps.synchronization.consumers import SyncConsumer

websocket_urlpatterns = [
    path("ws/sync/v1/", SyncConsumer.as_asgi()),
]
