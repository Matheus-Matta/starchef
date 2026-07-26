import django
from django.conf import settings
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application
from django.contrib.staticfiles.handlers import ASGIStaticFilesHandler

from config.env import configure_django_settings

configure_django_settings()
django.setup()

from apps.core.jwt_middleware import JwtAuthMiddlewareStack  # noqa: E402
from apps.core.ws_origin import build_ws_origin_validator  # noqa: E402
from config.routing import websocket_urlpatterns  # noqa: E402

django_asgi_app = get_asgi_application()
if settings.DEBUG:
    django_asgi_app = ASGIStaticFilesHandler(django_asgi_app)

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        # Web: valida Origin contra ALLOWED_HOSTS (bloqueia CSWSH). Nativo (sem
        # Origin, ex.: desktop Flutter): permitido, autentica por token.
        "websocket": build_ws_origin_validator(
            JwtAuthMiddlewareStack(URLRouter(websocket_urlpatterns))
        ),
    }
)
