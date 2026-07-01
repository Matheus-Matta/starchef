from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework_simplejwt.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.accounts.models import Account, GlobalSystemConfig, Permission, Plan, Role, Subscription, UserProfile
from apps.core.serializers import TenantModelSerializer

User = get_user_model()


class PermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Permission
        fields = ["id", "code", "name", "description", "created_at", "updated_at"]
        read_only_fields = ["id", "created_at", "updated_at"]


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class AccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = Account
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class SubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subscription
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class GlobalSystemConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSystemConfig
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


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
    password = serializers.CharField(write_only=True, required=True, min_length=8)

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

    def create(self, validated_data):
        profile_data = validated_data.pop("profile", {})
        password = validated_data.pop("password")
        request = self.context.get("request")
        account = getattr(request, "account", None) if request else None
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
            request = self.context.get("request")
            account = getattr(request, "account", None) if request else None
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

        if not self.user.is_superuser:
            if account is None:
                raise AuthenticationFailed("Usuario sem conta vinculada.", code="account_required")
            if not account.is_active or account.status != Account.STATUS_ACTIVE:
                raise AuthenticationFailed("Conta inativa.", code="account_inactive")
            if not profile.is_active:
                raise AuthenticationFailed("Perfil inativo.", code="profile_inactive")

        data["user"] = {
            "id": str(self.user.id),
            "username": self.user.username,
            "email": self.user.email,
            "name": self.user.get_full_name(),
            "profile_type": profile.profile_type if profile else None,
            "account_id": str(account.id) if account else None,
            "account_name": account.name if account else None,
            "restaurant_id": str(profile.restaurant_id) if profile and profile.restaurant_id else None,
            "restaurant_name": profile.restaurant.trade_name if profile and profile.restaurant_id else None,
            "branch_id": str(profile.branch_id) if profile and profile.branch_id else None,
            "branch_name": profile.branch.name if profile and profile.branch_id else None,
        }
        return data
