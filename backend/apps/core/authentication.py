from django.conf import settings
from rest_framework_simplejwt.authentication import JWTAuthentication


class CookieJWTAuthentication(JWTAuthentication):
    """Autentica pelo header `Authorization: Bearer` (compat / sessões temporárias)
    e, na ausência dele, pelo cookie httpOnly de access token.

    Proteção CSRF: os cookies usam `SameSite=Lax`, então NÃO são enviados em
    requisições POST/PUT/PATCH/DELETE cross-site — o vetor clássico de CSRF fica
    fechado sem precisar de token adicional. Requisições autenticadas por header
    (Bearer) não sofrem CSRF (o atacante não consegue definir headers cross-site).
    """

    def authenticate(self, request):
        header = self.get_header(request)
        raw_token = self.get_raw_token(header) if header is not None else None
        if raw_token is None:
            raw_token = request.COOKIES.get(settings.JWT_AUTH_COOKIE)
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
