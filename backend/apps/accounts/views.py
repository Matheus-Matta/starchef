from django.contrib.auth import get_user_model
from rest_framework import status, viewsets
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.accounts.models import Account, GlobalSystemConfig, Plan, Role, Subscription
from apps.accounts.serializers import (
    AccountSerializer,
    GlobalSystemConfigSerializer,
    PlanSerializer,
    RoleSerializer,
    StarChefTokenObtainPairSerializer,
    SubscriptionSerializer,
    UserSerializer,
)
from apps.core.mixins import AuditCreateUpdateMixin, TenantQuerySetMixin

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
                "branch_id": str(profile.branch_id) if profile and profile.branch_id else None,
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
            return queryset
        profile = getattr(user, "profile", None)
        if not profile or not profile.account_id:
            return queryset.none()
        queryset = queryset.filter(profile__account_id=profile.account_id)
        if not profile.restaurant_id:
            return queryset
        if profile.branch_id and profile.profile_type not in {"admin", "owner"}:
            queryset = queryset.filter(profile__branch_id=profile.branch_id)
        return queryset


class RoleViewSet(AuditCreateUpdateMixin, TenantQuerySetMixin, viewsets.ModelViewSet):
    serializer_class = RoleSerializer
    queryset = Role.all_objects.prefetch_related("permissions").all()
    search_fields = ["code", "name"]


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
