from apps.notifications.routing import websocket_urlpatterns as notification_websocket_urlpatterns
from apps.orders.routing import websocket_urlpatterns as order_websocket_urlpatterns
from apps.realtime.routing import websocket_urlpatterns as realtime_websocket_urlpatterns

websocket_urlpatterns = [
    *order_websocket_urlpatterns,
    *notification_websocket_urlpatterns,
    *realtime_websocket_urlpatterns,
]

