"""O bilhete de matrícula: uso único, prazo e dono.

O que estes testes protegem é a promessa de "uma vez só". Ela é fácil de
escrever e fácil de perder — basta alguém trocar o `select_for_update` por uma
leitura comum, ou gastar o bilhete fora da transação que provisiona.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.synchronization.models import SyncEnrollmentTicket
from apps.synchronization.services import crypto, enrollment

pytestmark = pytest.mark.django_db

User = get_user_model()


@pytest.fixture
def superusuario(db):
    return User.objects.create_superuser("root", "root@starchef.test", "senha-de-teste-123")


def _codigo(conta, **kwargs):
    _bilhete, codigo = enrollment.emitir_bilhete(conta=conta, **kwargs)
    return codigo


def test_o_codigo_em_claro_nao_fica_gravado(conta):
    """O banco guarda o hash. Um dump não vira um maço de credenciais."""
    bilhete, codigo = enrollment.emitir_bilhete(conta=conta, label="Loja Centro")

    assert bilhete.code_hash == crypto.hash_token(codigo)
    assert codigo not in str(bilhete.__dict__)
    assert len(codigo) > enrollment.MIN_SEGREDO


def test_matricular_gasta_o_bilhete(como_nuvem, conta, superusuario):
    codigo = _codigo(conta, label="Loja Centro")

    no, _envelope, _run = enrollment.enroll(
        username=superusuario.username, password="senha-de-teste-123",
        account_id=str(conta.id), enrollment_secret=codigo,
        node_name="Loja Centro", cloud_wss_url="wss://dev-sync.local/ws/sync/v1/",
    )

    bilhete = SyncEnrollmentTicket.objects.get(code_hash=crypto.hash_token(codigo))
    assert bilhete.used_at is not None
    assert bilhete.used_by_node_id == no.id
    assert not bilhete.utilizavel


def test_o_mesmo_bilhete_nao_matricula_duas_vezes(como_nuvem, conta, superusuario):
    """A promessa inteira do recurso em um assert."""
    codigo = _codigo(conta, label="Loja Centro")
    dados = {
        "username": superusuario.username, "password": "senha-de-teste-123",
        "account_id": str(conta.id), "enrollment_secret": codigo,
        "cloud_wss_url": "wss://dev-sync.local/ws/sync/v1/",
    }

    enrollment.enroll(node_name="Loja Centro", **dados)

    with pytest.raises(enrollment.EnrollmentRefused, match="já foi usado"):
        enrollment.enroll(node_name="Loja Segunda", **dados)


def test_bilhete_vencido_e_recusado(como_nuvem, conta, superusuario):
    codigo = _codigo(conta, label="Loja Centro")
    SyncEnrollmentTicket.objects.filter(code_hash=crypto.hash_token(codigo)).update(
        expires_at=timezone.now() - timezone.timedelta(minutes=1)
    )

    with pytest.raises(enrollment.EnrollmentRefused, match="venceu"):
        enrollment.enroll(
            username=superusuario.username, password="senha-de-teste-123",
            account_id=str(conta.id), enrollment_secret=codigo,
            node_name="Loja Centro", cloud_wss_url="wss://dev-sync.local/ws/sync/v1/",
        )


def test_bilhete_de_uma_conta_nao_matricula_em_outra(
    como_nuvem, conta, outra_conta, superusuario
):
    """Um bilhete é um convite para UMA conta, não uma senha de plataforma."""
    codigo = _codigo(outra_conta, label="Conta vizinha")

    with pytest.raises(enrollment.EnrollmentRefused, match="não pertence"):
        enrollment.enroll(
            username=superusuario.username, password="senha-de-teste-123",
            account_id=str(conta.id), enrollment_secret=codigo,
            node_name="Loja Centro", cloud_wss_url="wss://dev-sync.local/ws/sync/v1/",
        )


def test_segredo_combinado_continua_funcionando(como_nuvem, conta, superusuario):
    """O bilhete é aditivo: instalação que já existe não quebra.

    Um segredo que não corresponde a nenhum bilhete não é recusado — segue pelo
    caminho antigo. É isso que permite adotar o bilhete loja por loja em vez de
    num corte só.
    """
    segredo = "segredo-combinado-suficientemente-longo"

    no, _envelope, _run = enrollment.enroll(
        username=superusuario.username, password="senha-de-teste-123",
        account_id=str(conta.id), enrollment_secret=segredo,
        node_name="Loja Antiga", cloud_wss_url="wss://dev-sync.local/ws/sync/v1/",
    )

    assert no.account_id == conta.id
    assert not SyncEnrollmentTicket.objects.filter(used_at__isnull=False).exists()


def test_segredo_curto_continua_recusado(como_nuvem, conta, superusuario):
    with pytest.raises(enrollment.EnrollmentRefused, match="pelo menos"):
        enrollment.enroll(
            username=superusuario.username, password="senha-de-teste-123",
            account_id=str(conta.id), enrollment_secret="curto",
            node_name="Loja Centro", cloud_wss_url="wss://dev-sync.local/ws/sync/v1/",
        )


def test_codigo_desconhecido_nao_vira_bilhete(conta):
    """Nada de criar bilhete por acidente ao consultar um código qualquer."""
    antes = SyncEnrollmentTicket.objects.count()
    assert enrollment._consumir_bilhete("sc-" + uuid.uuid4().hex, conta, None) is None
    assert SyncEnrollmentTicket.objects.count() == antes
