import pytest


@pytest.mark.django_db
def test_auth_login_verify_and_refresh(api_client, manager_user):
    login_response = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123"},
        format="json",
    )

    assert login_response.status_code == 200
    assert login_response.data["access"]
    assert login_response.data["refresh"]
    assert login_response.data["user"]["account_id"]
    assert login_response.data["user"]["restaurant_name"] == "StarChef"
    assert login_response.data["user"]["branch_name"] == "Matriz"

    verify_response = api_client.post(
        "/api/v1/auth/verify/",
        {"token": login_response.data["access"]},
        format="json",
    )
    assert verify_response.status_code == 200

    me_response = api_client.get(
        "/api/v1/auth/me/",
        HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}",
    )
    assert me_response.status_code == 200
    assert me_response.data["restaurant_name"] == "StarChef"
    assert me_response.data["branch_name"] == "Matriz"

    invalid_verify_response = api_client.post(
        "/api/v1/auth/verify/",
        {"token": "invalid"},
        format="json",
    )
    assert invalid_verify_response.status_code == 401

    refresh_response = api_client.post(
        "/api/v1/auth/refresh/",
        {"refresh": login_response.data["refresh"]},
        format="json",
    )
    assert refresh_response.status_code == 200
    assert refresh_response.data["access"]


@pytest.mark.django_db
def test_token_expirado_responde_401_para_o_cliente_renovar(api_client, manager_user):
    """Um access token vencido é 401, nunca 403.

    O middleware de tenant recusa a requisição antes do DRF. Se ele respondesse
    403, o PDV mostraria "permissão insuficiente" para um operador cuja sessão
    apenas expirou, e a renovação automática — que dispara em 401 — nunca
    aconteceria.
    """
    from datetime import timedelta

    from rest_framework_simplejwt.tokens import AccessToken

    token = AccessToken.for_user(manager_user)
    token.set_exp(from_time=token.current_time - timedelta(hours=2), lifetime=timedelta(minutes=1))

    response = api_client.get("/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 401, response.content
    assert "WWW-Authenticate" in response
    assert "expirada" in response.json()["detail"].lower()


@pytest.mark.django_db
def test_token_malformado_tambem_responde_401(api_client):
    response = api_client.get("/api/v1/auth/me/", HTTP_AUTHORIZATION="Bearer nao-e-um-jwt")

    assert response.status_code == 401, response.content


@pytest.mark.django_db
def test_requisicao_sem_credencial_responde_401(api_client):
    """Sem credencial o problema é de autenticação, não de permissão.

    Responder 403 aqui fazia o PDV exibir "permissão insuficiente" e sugerir
    falar com o responsável pelo restaurante, quando bastava autenticar.
    """
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 401, response.content
    assert "WWW-Authenticate" in response


@pytest.mark.django_db
def test_usuario_sem_perfil_recebe_403_explicando_o_cadastro(api_client, db):
    """Autenticado, porém sem perfil: é problema de cadastro, não de token."""
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.tokens import AccessToken

    user = get_user_model().objects.create_user("sem-perfil", password="secret123")
    token = AccessToken.for_user(user)

    response = api_client.get("/api/v1/auth/me/", HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 403, response.content
    detail = response.json()["detail"].lower()
    assert "vinculado" in detail and "conta" in detail


@pytest.mark.django_db
def test_refresh_continua_aceito_com_access_vencido(api_client, manager_user):
    """A rota de refresh é pública: é justamente ela que resolve o 401."""
    login = api_client.post(
        "/api/v1/auth/login/",
        {"username": "manager", "password": "secret123"},
        format="json",
    )
    refresh_token = login.data["refresh"]

    response = api_client.post(
        "/api/v1/auth/refresh/",
        {"refresh": refresh_token},
        format="json",
        HTTP_AUTHORIZATION="Bearer token-vencido-e-invalido",
    )

    assert response.status_code == 200
    assert response.data["access"]
