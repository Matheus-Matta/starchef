import json
import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from django.urls import resolve
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from apps.core.authentication import CookieJWTAuthentication
from apps.accounts.models import Account
from apps.core.tenant import clear_current_account, set_current_account

logger = logging.getLogger(__name__)


PUBLIC_URL_NAMES = {
    "api-index",
    "healthcheck",
    "schema",
    "swagger-ui",
    "token_obtain_pair",
    "token_refresh",
    "token_verify",
    "password-reset",
    "password-reset-confirm",
}

# O Django admin tem autenticação e escopo de tenant próprios (TenantAdminMixin
# usa all_objects + X-Account-ID). Todo o /admin/ é isento do middleware de tenant
# — caso contrário, um usuário anônimo recebe 403 em /admin/ antes de o admin
# conseguir redirecioná-lo para a tela de login.
PUBLIC_PATH_PREFIXES = (
    "/admin/",
    settings.STATIC_URL,
    settings.MEDIA_URL,
)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        # Lê o JWT do header Authorization OU do cookie httpOnly.
        self.jwt_authentication = CookieJWTAuthentication()

    def __call__(self, request):
        try:
            if self.requires_tenant(request):
                if self.authenticate_jwt(request):
                    # A credencial foi apresentada e recusada (tipicamente um
                    # access token expirado). Isso é 401, não 403: o cliente
                    # precisa saber que deve renovar o token em vez de exibir
                    # "permissão insuficiente" para um operador que, na
                    # verdade, só está com a sessão vencida.
                    response = JsonResponse(
                        {"detail": "Credencial inválida ou expirada."},
                        status=401,
                    )
                    response["WWW-Authenticate"] = 'Bearer realm="api"'
                    return response
                user = getattr(request, "user", None)
                is_authenticated = bool(user and user.is_authenticated)
                account = self.resolve_account(request)
                if account is None:
                    if is_authenticated and user.is_superuser:
                        request.account = None
                        return self.get_response(request)
                    if not is_authenticated:
                        # Nenhuma credencial foi apresentada. Isso é 401 — o
                        # cliente precisa autenticar, não pedir permissão a
                        # alguém. Responder 403 aqui produzia a mensagem
                        # enganosa "permissão insuficiente" no PDV.
                        response = JsonResponse(
                            {"detail": "Autenticação necessária."},
                            status=401,
                        )
                        response["WWW-Authenticate"] = 'Bearer realm="api"'
                        return response
                    # Autenticado, mas o usuário não tem perfil ligado a uma
                    # conta. É um problema de cadastro, e a mensagem precisa
                    # dizer isso em vez de falar em permissão.
                    return JsonResponse(
                        {
                            "detail": (
                                "Seu usuário não está vinculado a nenhuma conta. "
                                "Peça ao responsável para associar um perfil ao seu login."
                            )
                        },
                        status=403,
                    )
                if not account.is_active or account.status != Account.STATUS_ACTIVE:
                    return JsonResponse({"detail": "A conta não está ativa."}, status=403)

                request.account = account
                set_current_account(account)
            else:
                request.account = None

            return self.get_response(request)
        finally:
            clear_current_account()

    def requires_tenant(self, request):
        if any(request.path.startswith(prefix) for prefix in PUBLIC_PATH_PREFIXES):
            return False
        try:
            match = resolve(request.path_info)
        except Http404:
            return False
        return match.url_name not in PUBLIC_URL_NAMES

    def authenticate_jwt(self, request):
        """Autentica pelo JWT do header ou do cookie.

        Devolve `True` quando havia uma credencial e ela foi recusada, para que
        o chamador responda 401. Uma requisição sem credencial nenhuma devolve
        `False` e segue o fluxo normal — quem decide ali é a resolução de conta.
        """
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            return False

        try:
            authenticated = self.jwt_authentication.authenticate(request)
        except (InvalidToken, TokenError, AuthenticationFailed):
            return True
        except Exception:
            # Falha inesperada (banco fora, por exemplo) não deve virar 401:
            # o pedido segue como anônimo e a camada seguinte decide.
            logger.exception("Falha inesperada ao autenticar o JWT")
            return False

        if authenticated:
            request.user, request.auth = authenticated
        return False

    def resolve_account(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        if user.is_superuser:
            if request.headers.get("X-Account-ID"):
                return Account.objects.filter(id=request.headers["X-Account-ID"], is_active=True).first()
            # Superusuários sem X-Account-ID operam no escopo global
            return None
        profile = getattr(user, "profile", None)
        return profile.account if profile else None


class TenantResponseSafetyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        account = getattr(request, "account", None)

        if account is None or not self.is_json_response(response):
            return response

        try:
            payload = json.loads(response.content.decode(response.charset or "utf-8"))
        except Exception:
            return response

        sanitized, blocked = self.sanitize_payload(payload, str(account.id))
        if blocked:
            logger.critical("Tenant response leak blocked", extra={"account_id": str(account.id), "path": request.path})
            return JsonResponse({"detail": "Não encontrado."}, status=404)

        if sanitized is not payload:
            response.content = json.dumps(sanitized).encode(response.charset or "utf-8")
            response["Content-Length"] = str(len(response.content))

        return response

    def is_json_response(self, response):
        return response.get("Content-Type", "").startswith("application/json") and hasattr(response, "content")

    def sanitize_payload(self, payload, account_id):
        if isinstance(payload, dict):
            if "account" in payload or "account_id" in payload:
                payload_account = payload.get("account_id", payload.get("account"))
                if payload_account is None or str(payload_account) != account_id:
                    return None, True

            sanitized = {}
            changed = False
            for key, value in payload.items():
                if isinstance(value, list):
                    clean_value = self.sanitize_list(value, account_id)
                    changed = changed or clean_value is not value
                    sanitized[key] = clean_value
                elif isinstance(value, dict):
                    clean_value, blocked = self.sanitize_payload(value, account_id)
                    if blocked:
                        return None, True
                    changed = changed or clean_value is not value
                    sanitized[key] = clean_value
                else:
                    sanitized[key] = value

            return sanitized if changed else payload, False

        if isinstance(payload, list):
            return self.sanitize_list(payload, account_id), False

        return payload, False

    def sanitize_list(self, rows, account_id):
        sanitized = []
        for row in rows:
            if not isinstance(row, dict) or ("account" not in row and "account_id" not in row):
                clean_row, blocked = self.sanitize_payload(row, account_id)
                if not blocked:
                    sanitized.append(clean_row)
                continue
            row_account = row.get("account_id", row.get("account"))
            if row_account is not None and str(row_account) == account_id:
                clean_row, blocked = self.sanitize_payload(row, account_id)
                if not blocked:
                    sanitized.append(clean_row)
        return sanitized
