import hashlib
import logging
import secrets
import string
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth import get_user_model, password_validation
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import PasswordResetRequest

logger = logging.getLogger(__name__)
User = get_user_model()
TOKEN_ALPHABET = string.ascii_letters + string.digits
GENERIC_MESSAGE = "Se o e-mail estiver cadastrado, enviaremos as instruções de redefinição."


def _token_hash(token):
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def _new_token(length=48):
    return "".join(secrets.choice(TOKEN_ALPHABET) for _ in range(length))


class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.RegexField(r"^[A-Za-z0-9]{48}$", write_only=True)
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)

    def validate(self, attrs):
        if attrs["password"] != attrs["password_confirm"]:
            raise serializers.ValidationError({"password_confirm": "As senhas não coincidem."})
        return attrs


class PasswordResetRateThrottle(ScopedRateThrottle):
    scope = "password_reset"


class PasswordResetConfirmRateThrottle(ScopedRateThrottle):
    scope = "password_reset_confirm"


class PasswordResetRequestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetRateThrottle]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        user = User.objects.filter(email__iexact=email, is_active=True).first()

        if user:
            raw_token = _new_token()
            expires_at = timezone.now() + timedelta(minutes=settings.PASSWORD_RESET_TIMEOUT_MINUTES)
            PasswordResetRequest.objects.filter(user=user, used_at__isnull=True).update(used_at=timezone.now())
            reset = PasswordResetRequest.objects.create(
                user=user,
                token_hash=_token_hash(raw_token),
                expires_at=expires_at,
            )
            params = urlencode({"token": raw_token})
            context = {
                "user": user,
                "reset_url": f"{settings.FRONTEND_URL}/redefinir-senha?{params}",
                "expires_minutes": settings.PASSWORD_RESET_TIMEOUT_MINUTES,
            }
            try:
                text_body = render_to_string("accounts/email/password_reset.txt", context)
                html_body = render_to_string("accounts/email/password_reset.html", context)
                message = EmailMultiAlternatives(
                    subject="Redefinição de senha — StarChef",
                    body=text_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                message.attach_alternative(html_body, "text/html")
                message.send(fail_silently=False)
            except Exception:
                # O cliente recebe a mesma resposta para nao revelar contas nem
                # detalhes do provedor. O erro operacional fica apenas nos logs.
                logger.exception("Falha ao enviar e-mail de redefinição", extra={"reset_id": reset.pk})

        return Response({"detail": GENERIC_MESSAGE}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [PasswordResetConfirmRateThrottle]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        now = timezone.now()

        with transaction.atomic():
            reset = (
                PasswordResetRequest.objects.select_for_update()
                .select_related("user")
                .filter(
                    token_hash=_token_hash(serializer.validated_data["token"]),
                    used_at__isnull=True,
                    expires_at__gt=now,
                    user__is_active=True,
                )
                .first()
            )
            if not reset:
                raise serializers.ValidationError({"token": "Link inválido, expirado ou já utilizado."})

            try:
                password_validation.validate_password(serializer.validated_data["password"], reset.user)
            except Exception as exc:
                raise serializers.ValidationError({"password": list(getattr(exc, "messages", [str(exc)]))}) from exc

            reset.user.set_password(serializer.validated_data["password"])
            reset.user.save(update_fields=["password"])
            PasswordResetRequest.objects.filter(user=reset.user, used_at__isnull=True).update(used_at=now)

        return Response({"detail": "Senha redefinida com sucesso."}, status=status.HTTP_200_OK)
