from apps.orders.routing import websocket_urlpatterns as order_websocket_urlpatterns

websocket_urlpatterns = [
    *order_websocket_urlpatterns,
]

