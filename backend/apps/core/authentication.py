from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.core.cookies import SCOPE_PANEL, SCOPE_STOREFRONT, access_cookie_name

# Header que diz de QUAL sessão a requisição é. O painel não manda nada (e cai
# no escopo padrão); o editor do storefront manda `storefront`.
AUTH_SCOPE_HEADER = "HTTP_X_AUTH_SCOPE"


def request_auth_scope(request):
    """Escopo de cookie pedido pela requisição. Valor inválido cai no painel."""
    raw = ""
    meta = getattr(request, "META", None)
    if meta:
        raw = str(meta.get(AUTH_SCOPE_HEADER) or "").strip().lower()
    return SCOPE_STOREFRONT if raw == SCOPE_STOREFRONT else SCOPE_PANEL


class CookieJWTAuthentication(JWTAuthentication):
    """Autentica pelo header `Authorization: Bearer` (compat / sessões temporárias)
    e, na ausência dele, pelo cookie httpOnly de access token.

    **Qual cookie?** O painel e o editor do storefront usam nomes diferentes
    (`sc_access` e `sf_access`) e podem estar abertos ao mesmo tempo, no mesmo
    navegador, com usuários diferentes. Ler "o que existir" seria não
    determinístico — a requisição do editor poderia ser atendida como o operador
    logado no painel. Por isso quem escolhe é o cliente, pelo header
    `X-Auth-Scope`, e a escolha só alcança cookies do PRÓPRIO navegador: não há
    ganho de privilégio em forjar o header, apenas a seleção de qual das
    sessões do próprio usuário vale.

    Proteção CSRF: os cookies usam `SameSite=Lax`, então NÃO são enviados em
    requisições POST/PUT/PATCH/DELETE cross-site — o vetor clássico de CSRF fica
    fechado sem precisar de token adicional. Requisições autenticadas por header
    (Bearer) não sofrem CSRF (o atacante não consegue definir headers cross-site).
    """

    def authenticate(self, request):
        header = self.get_header(request)
        raw_token = self.get_raw_token(header) if header is not None else None
        if raw_token is None:
            raw_token = request.COOKIES.get(access_cookie_name(request_auth_scope(request)))
        if not raw_token:
            return None

        validated_token = self.get_validated_token(raw_token)
        return self.get_user(validated_token), validated_token
