from django.urls import path

from .consumers import PdvRealtimeConsumer, RealtimeConsumer

websocket_urlpatterns = [
    path("ws/realtime/", RealtimeConsumer.as_asgi()),
    path("ws/pdv/<uuid:restaurant_id>/", PdvRealtimeConsumer.as_asgi()),
]
