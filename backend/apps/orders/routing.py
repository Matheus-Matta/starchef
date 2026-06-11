from django.urls import path

from apps.orders.consumers import KitchenConsumer

websocket_urlpatterns = [
    path("ws/kitchen/<uuid:branch_id>/<str:sector>/", KitchenConsumer.as_asgi()),
]

