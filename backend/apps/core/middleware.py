import json
import logging

from django.conf import settings
from django.http import Http404, JsonResponse
from django.urls import resolve
from rest_framework_simplejwt.authentication import JWTAuthentication

from apps.accounts.models import Account
from apps.core.tenant import clear_current_account, set_current_account

logger = logging.getLogger(__name__)


PUBLIC_URL_NAMES = {
    "healthcheck",
    "schema",
    "swagger-ui",
    "token_obtain_pair",
    "token_refresh",
    "token_verify",
}

PUBLIC_PATH_PREFIXES = (
    "/admin/login/",
    settings.STATIC_URL,
    settings.MEDIA_URL,
)


class TenantMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.jwt_authentication = JWTAuthentication()

    def __call__(self, request):
        try:
            if self.requires_tenant(request):
                self.authenticate_jwt(request)
                account = self.resolve_account(request)
                if account is None:
                    user = getattr(request, "user", None)
                    if user and user.is_authenticated and user.is_superuser:
                        request.account = None
                        return self.get_response(request)
                    return JsonResponse({"detail": "Account context is required."}, status=403)
                if not account.is_active or account.status != Account.STATUS_ACTIVE:
                    return JsonResponse({"detail": "Account is not active."}, status=403)

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
        if getattr(request, "user", None) is not None and request.user.is_authenticated:
            return

        try:
            authenticated = self.jwt_authentication.authenticate(request)
        except Exception:
            authenticated = None

        if authenticated:
            request.user, request.auth = authenticated

    def resolve_account(self, request):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        if user.is_superuser and request.headers.get("X-Account-ID"):
            return Account.objects.filter(id=request.headers["X-Account-ID"], is_active=True).first()
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
            return JsonResponse({"detail": "Not found."}, status=404)

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
