import re
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import PasswordResetRequest


@pytest.mark.django_db
def test_password_reset_is_generic_hashed_one_time_and_revokes_old_jwt(manager_user, settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.FRONTEND_URL = "https://app.starchef.test"
    client = APIClient()
    old_access = str(RefreshToken.for_user(manager_user).access_token)

    response = client.post("/api/v1/auth/password-reset/", {"email": manager_user.email}, format="json")
    assert response.status_code == 200
    assert len(mail.outbox) == 1

    match = re.search(r"token=([A-Za-z0-9]{48})", mail.outbox[0].body)
    assert match
    raw_token = match.group(1)
    stored = PasswordResetRequest.objects.get(user=manager_user)
    assert raw_token not in stored.token_hash
    assert re.fullmatch(r"[a-f0-9]{64}", stored.token_hash)

    confirm = client.post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "token": raw_token,
            "password": "Nova-Senha-Segura-2026!",
            "password_confirm": "Nova-Senha-Segura-2026!",
        },
        format="json",
    )
    assert confirm.status_code == 200
    manager_user.refresh_from_db()
    assert manager_user.check_password("Nova-Senha-Segura-2026!")

    replay = client.post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "token": raw_token,
            "password": "Outra-Senha-Segura-2026!",
            "password_confirm": "Outra-Senha-Segura-2026!",
        },
        format="json",
    )
    assert replay.status_code == 400

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {old_access}")
    assert client.get("/api/v1/auth/me/").status_code in {401, 403}


@pytest.mark.django_db
def test_password_reset_does_not_reveal_unknown_email(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    client = APIClient()

    known_shape = client.post("/api/v1/auth/password-reset/", {"email": "unknown@example.com"}, format="json")

    assert known_shape.status_code == 200
    assert known_shape.data["detail"] == (
        "Se o e-mail estiver cadastrado, enviaremos as instruções de redefinição."
    )
    assert len(mail.outbox) == 0


@pytest.mark.django_db
def test_expired_password_reset_token_is_rejected(manager_user):
    from apps.accounts.password_reset import _new_token, _token_hash

    token = _new_token()
    PasswordResetRequest.objects.create(
        user=manager_user,
        token_hash=_token_hash(token),
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    response = APIClient().post(
        "/api/v1/auth/password-reset/confirm/",
        {
            "token": token,
            "password": "Nova-Senha-Segura-2026!",
            "password_confirm": "Nova-Senha-Segura-2026!",
        },
        format="json",
    )

    assert response.status_code == 400
