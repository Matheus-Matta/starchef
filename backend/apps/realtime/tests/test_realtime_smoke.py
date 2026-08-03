"""Smoke test do app realtime (Channels/WebSocket, sem endpoint REST).

Confirma que o roteamento e os consumers importam e instanciam sem erro —
o jeito mais barato de detectar um import quebrado antes de descobrir em
produção que o WebSocket não sobe.
"""
from apps.realtime.consumers import RealtimeConsumer
from apps.realtime.events import account_group
from apps.realtime.routing import websocket_urlpatterns


def test_websocket_urlpatterns_registered():
    assert len(websocket_urlpatterns) >= 1


def test_realtime_consumer_instantiates():
    consumer = RealtimeConsumer()
    assert consumer is not None


def test_account_group_name_is_deterministic():
    assert account_group("abc") == account_group("abc")
    assert account_group("abc") != account_group("def")
