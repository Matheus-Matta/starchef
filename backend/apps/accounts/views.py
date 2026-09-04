from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from apps.core.permissions import effective_permission_codes
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.core.cookies import clear_auth_cookies, set_auth_cookies

from apps.accounts.limits import assert_can_create_user
from apps.accounts.models import Account, CosmosConfig, FocusNfeConfig, GlobalSystemConfig, Permission, Plan, Role, Subscription
from apps.accounts.serializers import (
    AccountSerializer,
    CosmosConfigSerializer,
    FocusNfeConfigSerializer,
    GlobalSystemConfigSerializer,
    PermissionSerializer,
    PlanSerializer,
    RoleSerializer,
    StarChefTokenObtainPairSerializer,
    SubscriptionSerializer,
    UserSerializer,
    resolve_enabled_modules,
)
from apps.core.access import is_tenant_admin
from apps.core.viewsets import ReadOnlyTenantViewSet

User = get_user_model()


class FocusNfeConfigView(APIView):
    """Consulta e edita a configuracao Focus da conta autenticada."""

    required_module = "financeiro"

    def _account_config(self, request):
        account = getattr(request, "account", None)
        if account is None:
            raise PermissionDenied("Conta nao identificada.")
        config, _ = FocusNfeConfig.objects.get_or_create(account=account)
        return config

    def _assert_admin(self, request):
        if not is_tenant_admin(request.user):
            raise PermissionDenied("Apenas administradores da conta podem configurar a Focus NFe.")

    def get(self, request):
        self._assert_admin(request)
        return Response(FocusNfeConfigSerializer(self._account_config(request)).data)

    def patch(self, request):
        self._assert_admin(request)
        config = self._account_config(request)
        serializer = FocusNfeConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class CosmosConfigView(APIView):
    """Consulta e edita a credencial Cosmos da conta autenticada."""

    required_module = "financeiro"

    def _account_config(self, request):
        account = getattr(request, "account", None)
        if account is None:
            raise PermissionDenied("Conta nao identificada.")
        config, _ = CosmosConfig.objects.get_or_create(account=account)
        return config

    def _assert_admin(self, request):
        if not is_tenant_admin(request.user):
            raise PermissionDenied("Apenas administradores da conta podem configurar a Cosmos.")

    def get(self, request):
        self._assert_admin(request)
        return Response(CosmosConfigSerializer(self._account_config(request)).data)

    def patch(self, request):
        self._assert_admin(request)
        config = self._account_config(request)
        serializer = CosmosConfigSerializer(config, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class LoginView(TokenObtainPairView):
    serializer_class = StarChefTokenObtainPairSerializer
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request, *args, **kwargs):
        response = super().post(request, *args, **kwargs)
        # Grava os tokens em cookies httpOnly — salvo em login "temporário"
        # (ex.: autorização gerencial no caixa), que não deve mexer na sessão.
        if response.status_code == status.HTTP_200_OK and not request.data.get("no_cookie"):
            set_auth_cookies(response, access=response.data.get("access"), refresh=response.data.get("refresh"))
        return response


class CookieTokenRefreshView(TokenRefreshView):
    """Renova o access token lendo o refresh do cookie (fallback: corpo)."""

    # O refresh é anônimo (sem access válido), então o UserRateThrottle global não
    # o cobre bem. Escopo próprio evita abuso de rotação de tokens.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "token_refresh"

    def post(self, request, *args, **kwargs):
        data = request.data.copy() if hasattr(request.data, "copy") else dict(request.data)
        if not data.get("refresh"):
            cookie_refresh = request.COOKIES.get(settings.JWT_AUTH_REFRESH_COOKIE)
            if cookie_refresh:
                data["refresh"] = cookie_refresh

        serializer = self.get_serializer(data=data)
        try:
            serializer.is_valid(raise_exception=True)
        except TokenError as exc:
            raise InvalidToken(exc.args[0])

        response = Response(serializer.validated_data, status=status.HTTP_200_OK)
        set_auth_cookies(response, access=serializer.validated_data.get("access"), refresh=serializer.validated_data.get("refresh"))
        return response


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh") or request.COOKIES.get(settings.JWT_AUTH_REFRESH_COOKIE)
        if refresh:
            try:
                RefreshToken(refresh).blacklist()
            except TokenError:
                pass  # já inválido/expirado — encerrar a sessão mesmo assim
        response = Response(status=status.HTTP_204_NO_CONTENT)
        # A sessão temporária (gerente) não deve limpar os cookies do operador.
        if not request.data.get("no_cookie"):
            clear_auth_cookies(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, "profile", None)
        account = getattr(request, "account", None) or (profile.account if profile and profile.account_id else None)
        return Response(
            {
                "id": str(request.user.id),
                "username": request.user.username,
                "email": request.user.email,
                "name": request.user.get_full_name(),
                "is_superuser": request.user.is_superuser,
                "profile_type": profile.role.code if profile and profile.role_id else None,
                "account_id": str(account.id) if account else None,
                "account_name": account.name if account else None,
                "restaurant_id": str(profile.restaurant_id) if profile and profile.restaurant_id else None,
                "restaurant_name": profile.restaurant.trade_name if profile and profile.restaurant_id else None,
                "branch_id": str(profile.branch_id) if profile and profile.branch_id else None,
                "branch_name": profile.branch.name if profile and profile.branch_id else None,
                "enabled_modules": resolve_enabled_modules(request.user, account),
                "permissions": sorted(effective_permission_codes(request.user)),
            }
        )


class AdminAuthorizationView(APIView):
    """Confirma credenciais autorizadas sem trocar a sessão do operador.

    Sem ``permission`` preserva o fluxo de fechamento do aplicativo, exclusivo
    para administradores. Para uma operação conhecida, também aceita um usuário
    da mesma conta que possua explicitamente a permissão solicitada.
    """

    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "cash_approval"

    def post(self, request):
        login = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")
        required_permission = str(request.data.get("permission") or "").strip()
        if required_permission not in {"", "orders.cancel"}:
            return Response(
                {"detail": "Operação de autorização inválida."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not login or not password:
            return Response(
                {"detail": "Informe o usuário e a senha do administrador."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        username = login
        if "@" in login:
            matched = User.objects.filter(email__iexact=login).only("username").first()
            if matched is not None:
                username = matched.get_username()
        administrator = authenticate(request=request, username=username, password=password)
        if administrator is None:
            return Response(
                {"detail": "Credenciais de administrador inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        profile = getattr(administrator, "profile", None)
        request_account = getattr(request, "account", None)
        same_account = bool(
            request_account is not None
            and profile is not None
            and profile.account_id == request_account.id
        )
        permission_codes = effective_permission_codes(administrator)
        has_required_permission = (
            not required_permission
            and is_tenant_admin(administrator)
        ) or (
            bool(required_permission)
            and (
                is_tenant_admin(administrator)
                or "*" in permission_codes
                or required_permission in permission_codes
            )
        )
        if not same_account or not profile.is_active or not has_required_permission:
            # Uma resposta única evita revelar se o usuário existe em outra
            # conta ou apenas não possui perfil administrativo.
            return Response(
                {"detail": "Credenciais sem permissão para esta operação na conta."},
                status=status.HTTP_403_FORBIDDEN,
            )

        return Response({"authorized": True, "user_id": str(administrator.id)})


class UserViewSet(viewsets.ModelViewSet):
    serializer_class = UserSerializer
    search_fields = ["username", "email", "first_name", "last_name"]
    ordering_fields = ["username", "email", "last_login"]

    def get_queryset(self):
        queryset = User.objects.select_related(
            "profile",
            "profile__account",
            "profile__restaurant",
            "profile__branch",
            "profile__role",
        )
        user = self.request.user
        if user.is_superuser:
            # Superusuário também é escopado por conta na API: a conta vem do
            # header X-Account-ID ou do próprio perfil (TenantMiddleware).
            # Sem conta resolvida não há listagem — ver todas as contas de uma
            # vez é papel do /admin.
            account = getattr(self.request, "account", None)
            if account is None:
                return queryset.none()
            return self._filter_users_by_selected_scope(queryset.filter(profile__account_id=account.id))
        profile = getattr(user, "profile", None)
        if not profile or not profile.account_id:
            return queryset.none()
        queryset = queryset.filter(profile__account_id=profile.account_id)
        if is_tenant_admin(user):
            return self._filter_users_by_selected_scope(queryset)
        if not profile.restaurant_id:
            return queryset.none()
        queryset = queryset.filter(profile__restaurant_id=profile.restaurant_id)
        if profile.branch_id:
            queryset = queryset.filter(profile__branch_id=profile.branch_id)
        return queryset

    def _filter_users_by_selected_scope(self, queryset):
        restaurant_id = self.request.query_params.get("restaurant")
        branch_id = self.request.query_params.get("branch")
        if restaurant_id:
            queryset = queryset.filter(profile__restaurant_id=restaurant_id)
        if branch_id:
            queryset = queryset.filter(profile__branch_id=branch_id)
        return queryset

    def perform_create(self, serializer):
        # Aplica o limite de usuários da conta antes de criar (superadmin isento).
        if not self.request.user.is_superuser:
            assert_can_create_user(getattr(self.request, "account", None))
        super().perform_create(serializer)


class RoleViewSet(ReadOnlyTenantViewSet):
    """Perfis de Acesso agora sao fixos (ver apps.accounts.role_catalog).

    Somente leitura: nao ha mais criacao, edicao ou remocao de perfis pela API
    — os 4 perfis (Garcom, Caixa, Gerente, Administrador) sao provisionados
    por conta via signal (contas novas) e migration (contas existentes).
    """

    serializer_class = RoleSerializer
    queryset = Role.all_objects.prefetch_related("permissions").all()
    search_fields = ["code", "name"]


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista as permissões de negócio disponíveis (catálogo global, somente leitura).

    Usado para preencher o seletor de permissões na tela de Perfil de acesso.
    """

    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()
    search_fields = ["code", "name", "group"]
    ordering_fields = ["name", "code", "group", "sort_order"]
    ordering = ["module", "sort_order", "name"]  # agrupado e na ordem do catálogo
    pagination_class = None  # catálogo pequeno: retorna todas de uma vez


class PlanViewSet(viewsets.ModelViewSet):
    serializer_class = PlanSerializer
    queryset = Plan.objects.all()
    search_fields = ["code", "name"]

    def get_queryset(self):
        if not self.request.user.is_superuser:
            return Plan.objects.filter(is_active=True)
        return super().get_queryset()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Apenas superadmin pode criar planos.")
        serializer.save()


class AccountViewSet(viewsets.ModelViewSet):
    serializer_class = AccountSerializer
    queryset = Account.objects.select_related("plan").all()
    search_fields = ["name", "slug", "document", "email"]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return super().get_queryset()
        account = getattr(self.request, "account", None)
        return super().get_queryset().filter(pk=account.pk) if account else Account.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Apenas superadmin pode criar contas.")
        serializer.save()


class SubscriptionViewSet(viewsets.ModelViewSet):
    serializer_class = SubscriptionSerializer
    queryset = Subscription.objects.select_related("account", "plan").all()

    def get_queryset(self):
        if self.request.user.is_superuser:
            return super().get_queryset()
        account = getattr(self.request, "account", None)
        return super().get_queryset().filter(account=account) if account else Subscription.objects.none()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Apenas superadmin pode criar assinaturas.")
        serializer.save()


class GlobalSystemConfigViewSet(viewsets.ModelViewSet):
    serializer_class = GlobalSystemConfigSerializer
    queryset = GlobalSystemConfig.objects.all()
    search_fields = ["key", "description"]

    def get_queryset(self):
        if not self.request.user.is_superuser:
            return GlobalSystemConfig.objects.none()
        return super().get_queryset()

    def perform_create(self, serializer):
        if not self.request.user.is_superuser:
            raise PermissionDenied("Apenas superadmin pode alterar configuracoes globais.")
        serializer.save()
