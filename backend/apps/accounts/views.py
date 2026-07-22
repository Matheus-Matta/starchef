from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import Account, GlobalSystemConfig, Permission, Plan, Role, Subscription
from apps.accounts.serializers import (
    AccountSerializer,
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
from apps.core.viewsets import BaseTenantViewSet

User = get_user_model()


class LoginView(TokenObtainPairView):
    serializer_class = StarChefTokenObtainPairSerializer


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if refresh:
            try:
                token = RefreshToken(refresh)
                token.blacklist()
            except TokenError:
                return Response({"detail": "Refresh token invalido."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                "profile_type": profile.profile_type if profile else None,
                "account_id": str(account.id) if account else None,
                "account_name": account.name if account else None,
                "restaurant_id": str(profile.restaurant_id) if profile and profile.restaurant_id else None,
                "restaurant_name": profile.restaurant.trade_name if profile and profile.restaurant_id else None,
                "branch_id": str(profile.branch_id) if profile and profile.branch_id else None,
                "branch_name": profile.branch.name if profile and profile.branch_id else None,
                "enabled_modules": resolve_enabled_modules(request.user, account),
            }
        )


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
            return self._filter_users_by_selected_scope(queryset)
        profile = getattr(user, "profile", None)
        if not profile or not profile.account_id:
            return queryset.none()
        queryset = queryset.filter(profile__account_id=profile.account_id)
        if is_tenant_admin(user):
            return self._filter_users_by_selected_scope(queryset)
        if not profile.restaurant_id:
            return queryset.none()
        queryset = queryset.filter(profile__restaurant_id=profile.restaurant_id)
        if profile.branch_id and profile.profile_type not in {"admin", "owner"}:
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


class RoleViewSet(BaseTenantViewSet):
    serializer_class = RoleSerializer
    queryset = Role.all_objects.prefetch_related("permissions").all()
    search_fields = ["code", "name"]


class PermissionViewSet(viewsets.ReadOnlyModelViewSet):
    """Lista as permissões de negócio disponíveis (catálogo global, somente leitura).

    Usado para preencher o seletor de permissões na tela de Perfil de acesso.
    """

    serializer_class = PermissionSerializer
    queryset = Permission.objects.all()
    search_fields = ["code", "name"]
    ordering_fields = ["name", "code"]
    ordering = ["name"]
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
