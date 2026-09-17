from apps.notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from apps.orders.routing import websocket_urlpatterns as order_websocket_urlpatterns
from apps.realtime.routing import websocket_urlpatterns as realtime_websocket_urlpatterns
from apps.synchronization.routing import websocket_urlpatterns as sync_websocket_urlpatterns

websocket_urlpatterns = [
    *order_websocket_urlpatterns,
    *notification_websocket_urlpatterns,
    *realtime_websocket_urlpatterns,
    # Sincronização backend-to-backend: só o nó CLOUD atende esta rota; o nó
    # LOCAL é quem disca para cá (ver apps/synchronization/services/transport.py).
    *sync_websocket_urlpatterns,
]

