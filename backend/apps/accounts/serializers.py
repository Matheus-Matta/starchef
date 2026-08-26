from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Account, GlobalSystemConfig, Permission, Plan, Role, Subscription, UserProfile
from apps.core.modules import ALL_MODULES, account_active_modules
from apps.core.serializers import TIMESTAMP_READ_ONLY_FIELDS, TenantModelSerializer

User = get_user_model()


def resolve_enabled_modules(user, account):
    """Modulos que a UI deve liberar. Superuser (dono da plataforma) enxerga todos."""
    if user.is_superuser:
        return list(ALL_MODULES)
    return account_active_modules(account)


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "name", "description", "group", "module", "sort_order", "created_at", "updated_at"]
        read_only_fields = TIMESTAMP_READ_ONLY_FIELDS


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = TIMESTAMP_READ_ONLY_FIELDS


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = "__all__"
        read_only_fields = TIMESTAMP_READ_ONLY_FIELDS


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = "__all__"
        read_only_fields = TIMESTAMP_READ_ONLY_FIELDS


class GlobalSystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSystemConfig
        fields = "__all__"
        read_only_fields = TIMESTAMP_READ_ONLY_FIELDS


class RoleSerializer(TenantModelSerializer):
    class Meta:
        model = Role
        fields = [
            "id",
            "account",
            "code",
            "name",
            "restaurant",
            "permissions",
            "max_discount_percent",
            "is_account_admin",
            "is_system",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "account", "created_at", "updated_at"]


class UserProfileSerializer(TenantModelSerializer):
    role_name = serializers.CharField(source="role.name", read_only=True)
    restaurant_name = serializers.CharField(source="restaurant.trade_name", read_only=True)
    branch_name = serializers.CharField(source="branch.name", read_only=True)

    class Meta:
        model = UserProfile
        fields = [
            "id",
            "phone",
            "profile_type",
            "account",
            "role",
            "role_name",
            "restaurant",
            "restaurant_name",
            "branch",
            "branch_name",
            "specific_permissions",
            "last_login_at",
            "is_active",
        ]
        read_only_fields = ["id", "account", "last_login_at"]


class UserSerializer(serializers.ModelSerializer):
    profile = UserProfileSerializer()
    # Obrigatória só na criação (validada no create). Na edição, em branco = manter.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=8)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "password",
            "is_active",
            "last_login",
            "profile",
        ]
        read_only_fields = ["id", "last_login"]

    def validate_email(self, value):
        # Unicidade case-insensitive, alinhada ao login por email.
        if not value:
            return value
        qs = User.objects.filter(email__iexact=value)
        if self.instance is not None:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise serializers.ValidationError("Ja existe um usuario com este email.")
        return value

    def _request_account(self):
        request = self.context.get("request")
        if request is None:
            return None
        account = getattr(request, "account", None)
        if account is not None or not request.user.is_superuser:
            return account
        profile = getattr(request.user, "profile", None)
        return profile.account if profile and profile.account_id else None

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password", "")
        if not password:
            raise serializers.ValidationError({"password": "Informe uma senha para criar o usuário."})
        account = self._request_account()
        if account:
            profile_data["account"] = account
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        UserProfile.objects.create(user=user, **profile_data)
        return user

    def update(self, instance, validated_data):
        profile_data = validated_data.pop("profile", None)
        password = validated_data.pop("password", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if profile_data is not None:
            account = self._request_account()
            defaults = {"account": account} if account else {}
            profile, _ = UserProfile.all_objects.get_or_create(user=instance, defaults=defaults)
            if account:
                profile.account = account
            for attr, value in profile_data.items():
                setattr(profile, attr, value)
            profile.save()
        return instance


class StarChefTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        login = attrs.get(self.username_field)
        if login and "@" in login:
            user = User.objects.filter(email__iexact=login).first()
            if user:
                attrs[self.username_field] = user.get_username()

        data = super().validate(attrs)
        profile = getattr(self.user, "profile", None)
        account = profile.account if profile and profile.account_id else None

        # Conta vinculada é obrigatória para TODO mundo, superusuário incluído:
        # no app ele opera como admin da própria conta (a visão de todas as
        # contas é o /admin). Sem vínculo, o app abriria vazio/403 em toda tela
        # — melhor barrar aqui, onde a mensagem aparece na tela de login.
        if account is None:
            raise AuthenticationFailed(
                "Usuario sem conta vinculada."
                if not self.user.is_superuser
                else "Usuario de plataforma sem conta vinculada. Use o /admin ou vincule um perfil a uma conta.",
                code="account_required",
            )

        # Conta inativa vale para o superusuário também: o TenantMiddleware
        # bloqueia (403 "A conta não está ativa.") sem exceção, então deixá-lo
        # logar só produziria uma sessão que erra em toda tela.
        if not account.is_active or account.status != Account.STATUS_ACTIVE:
            raise AuthenticationFailed("Conta inativa.", code="account_inactive")
        if not profile.is_active:
            raise AuthenticationFailed("Perfil inativo.", code="profile_inactive")

        request = self.context.get("request")
        if (
            request is not None
            and request.data.get("client") == "waiter_app"
            and profile.profile_type != UserProfile.PROFILE_WAITER
        ):
            raise AuthenticationFailed(
                "Use uma conta com perfil de garçom para entrar neste aplicativo.",
                code="waiter_profile_required",
            )

        data["user"] = {
            "id": str(self.user.id),
            "username": self.user.username,
            "email": self.user.email,
            "name": self.user.get_full_name(),
            "is_superuser": self.user.is_superuser,
            "profile_type": profile.profile_type if profile else None,
            "account_id": str(account.id) if account else None,
            "account_name": account.name if account else None,
            "restaurant_id": str(profile.restaurant_id) if profile and profile.restaurant_id else None,
            "restaurant_name": profile.restaurant.trade_name if profile and profile.restaurant_id else None,
            "branch_id": str(profile.branch_id) if profile and profile.branch_id else None,
            "branch_name": profile.branch.name if profile and profile.branch_id else None,
            "enabled_modules": resolve_enabled_modules(self.user, account),
            "permissions": self._permission_codes(),
        }
        return data

    def _permission_codes(self):
        from apps.core.permissions import effective_permission_codes

        return sorted(effective_permission_codes(self.user))
