"""Autorizacao de divergencia de caixa feita com o PDV offline.

Um caixa que fecha com diferenca precisa da senha de acoes do restaurante para
ser encerrado. Sem internet, o terminal ja sabe conferir essa senha — ele
guarda o hash PBKDF2 justamente para isso. O que faltava era o servidor
reconhecer essa autorizacao no replay.

A senha em texto **nao** entra na fila local: o terminal prova que possui o
hash devolvendo um HMAC-SHA256 dele sobre ``{cash_register_id}:{nonce}``.
Guardar a senha em disco seria pior do que a espera que a autorizacao offline
evita.
"""

import hashlib
import hmac
from decimal import Decimal

import pytest
from django.contrib.auth.hashers import make_password
from rest_framework_simplejwt.tokens import AccessToken

from apps.payments.models import CashRegister, CashStation


@pytest.fixture
def authenticated(api_client, waiter_user):
    # De proposito um operador comum: sem senha nem prova, a autorizacao
    # exigiria gerente.
    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(waiter_user)}"
    )
    return api_client


@pytest.fixture
def cash_password(restaurant):
    restaurant.cash_action_password = make_password("1234")
    restaurant.save(update_fields=["cash_action_password"])
    return restaurant.cash_action_password


@pytest.fixture
def divergent_register(account, restaurant, branch, waiter_user):
    station = CashStation.objects.create(
        account=account, restaurant=restaurant, name="Caixa 1"
    )
    return CashRegister.objects.create(
        account=account,
        restaurant=restaurant,
        branch=branch,
        cash_station=station,
        opened_by=waiter_user,
        opening_amount=Decimal("100.00"),
        status=CashRegister.STATUS_PENDING_APPROVAL,
    )


def _proof(stored_hash, cash_register_id, nonce):
    return hmac.new(
        str(stored_hash).encode("utf-8"),
        f"{cash_register_id}:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


@pytest.mark.django_db
def test_prova_do_terminal_autoriza_sem_a_senha_em_texto(
    authenticated, divergent_register, cash_password
):
    response = authenticated.post(
        f"/api/v1/cash-register/{divergent_register.pk}/approve/",
        {
            "reason": "Diferenca conferida com o gerente por telefone.",
            "cash_password_proof": _proof(
                cash_password, divergent_register.pk, "nonce-1"
            ),
            "proof_nonce": "nonce-1",
        },
        format="json",
    )

    assert response.status_code == 200, response.content
    divergent_register.refresh_from_db()
    assert divergent_register.approved_at is not None


@pytest.mark.django_db
def test_prova_invalida_e_recusada(authenticated, divergent_register, cash_password):
    response = authenticated.post(
        f"/api/v1/cash-register/{divergent_register.pk}/approve/",
        {
            "reason": "Tentativa.",
            "cash_password_proof": "prova-inventada",
            "proof_nonce": "nonce-1",
        },
        format="json",
    )

    assert response.status_code == 400
    divergent_register.refresh_from_db()
    assert divergent_register.approved_at is None


@pytest.mark.django_db
def test_prova_de_outra_operacao_nao_serve(
    authenticated, divergent_register, cash_password
):
    # O nonce entra na mensagem: uma prova gerada para outra autorizacao nao
    # pode ser reaproveitada.
    response = authenticated.post(
        f"/api/v1/cash-register/{divergent_register.pk}/approve/",
        {
            "reason": "Tentativa.",
            "cash_password_proof": _proof(
                cash_password, divergent_register.pk, "outro-nonce"
            ),
            "proof_nonce": "nonce-1",
        },
        format="json",
    )

    assert response.status_code == 400


@pytest.mark.django_db
def test_sem_senha_nem_prova_continua_exigindo_gerente(
    authenticated, divergent_register, cash_password
):
    response = authenticated.post(
        f"/api/v1/cash-register/{divergent_register.pk}/approve/",
        {"reason": "Sem autorizacao nenhuma."},
        format="json",
    )

    # O que importa e a invariante: sem autorizacao nenhuma, o caixa nao e
    # aprovado. O codigo exato varia (400 por validacao, 403 por permissao,
    # 429 quando o limitador de tentativas ja foi acionado por outro teste).
    assert response.status_code >= 400
    divergent_register.refresh_from_db()
    assert divergent_register.approved_at is None
