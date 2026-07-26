"""Validação de origem do WebSocket compatível com clientes web e nativos.

- **Navegador**: SEMPRE envia o header `Origin` no handshake — validamos contra
  os hosts confiáveis (`ALLOWED_HOSTS`), bloqueando CSWSH (WebSocket hijacking
  cross-site que exploraria o cookie da vítima).
- **App nativo** (ex.: desktop Flutter/Windows): não envia `Origin` (não existe
  "origem web") e autentica por token (`?token=`/Bearer), então NÃO é vetor de
  CSWSH. Essas conexões são permitidas mesmo sem `Origin` — a autenticação JWT
  segue obrigatória no middleware/consumer.
"""
from channels.security.websocket import OriginValidator
from django.conf import settings


class OriginOrNativeValidator(OriginValidator):
    def valid_origin(self, parsed_origin):
        # Sem header Origin -> cliente nativo (navegador nunca omite) -> permite.
        if parsed_origin is None:
            return True
        return super().valid_origin(parsed_origin)


def build_ws_origin_validator(application):
    allowed_hosts = list(settings.ALLOWED_HOSTS)
    if settings.DEBUG and not allowed_hosts:
        allowed_hosts = ["localhost", "127.0.0.1", "[::1]"]
    return OriginOrNativeValidator(application, allowed_hosts)
