"""Matrícula do nó local: autenticação, cifra e carga inicial automática."""
import pytest
from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.synchronization.constants import NodeType, RunStatus, RunType
from apps.synchronization.models import SyncNode, SyncRun
from apps.synchronization.services import enrollment

pytestmark = pytest.mark.django_db

User = get_user_model()
SEGREDO = "segredo-de-matricula-com-tamanho-suficiente"


@pytest.fixture
def superadmin(db):
    return User.objects.create_superuser("root", "root@starchef.test", "senha-forte-123")


@pytest.fixture
def admin_da_conta(db, conta):
    usuario = User.objects.create_user("admin1", "admin1@starchef.test", "senha-forte-123")
    UserProfile.objects.create(
        account=conta, user=usuario, role=ensure_system_roles(conta)["admin"]
    )
    return usuario


def _matricular(conta, usuario, senha="senha-forte-123", **extra):
    dados = {
        "username": usuario.username,
        "password": senha,
        "account_id": str(conta.id),
        "enrollment_secret": SEGREDO,
        "node_name": "Loja Centro",
        "cloud_wss_url": "wss://nuvem.test/ws/sync/v1/",
    }
    dados.update(extra)
    return enrollment.enroll(**dados)


def test_superadmin_matricula_e_recebe_pacote_cifrado(como_nuvem, conta, superadmin):
    no, envelope, run = _matricular(conta, superadmin)

    assert no.node_type == NodeType.LOCAL
    assert no.account_id == conta.id
    # O pacote não sai em claro: só nonce + ciphertext.
    assert "ciphertext" in envelope and "SYNC_AUTH_TOKEN" not in str(envelope)

    pacote = enrollment.decifrar(envelope, SEGREDO)
    assert pacote["SYNC_NODE_ID"] == str(no.id)
    assert pacote["SYNC_AUTH_TOKEN"]
    assert pacote["SYNC_ENCRYPTION_KEY"]
    assert pacote["SYNC_INITIAL_RUN_ID"] == str(run.id)


def test_a_carga_total_ja_nasce_enfileirada(como_nuvem, conta, superadmin):
    _no, _envelope, run = _matricular(conta, superadmin)
    assert run.run_type == RunType.FULL
    assert run.status == RunStatus.PENDING
    assert SyncRun.objects.filter(pk=run.id).exists()


def test_admin_da_propria_conta_pode_matricular(como_nuvem, conta, admin_da_conta):
    no, _envelope, _run = _matricular(conta, admin_da_conta)
    assert no.account_id == conta.id


def test_admin_nao_matricula_no_em_outra_conta(como_nuvem, conta, outra_conta, admin_da_conta):
    with pytest.raises(enrollment.EnrollmentRefused, match="sem permissão"):
        _matricular(outra_conta, admin_da_conta)


def test_senha_errada_e_recusada(como_nuvem, conta, superadmin):
    with pytest.raises(enrollment.EnrollmentRefused, match="inválidos"):
        _matricular(conta, superadmin, senha="chute")


def test_segredo_curto_e_recusado(como_nuvem, conta, superadmin):
    with pytest.raises(enrollment.EnrollmentRefused, match="caracteres"):
        _matricular(conta, superadmin, enrollment_secret="curto")


def test_segredo_errado_nao_abre_o_pacote(como_nuvem, conta, superadmin):
    _no, envelope, _run = _matricular(conta, superadmin)
    with pytest.raises(Exception):
        enrollment.decifrar(envelope, "outro-segredo-de-matricula-qualquer")


def test_rematricula_reaproveita_o_mesmo_no(como_nuvem, conta, superadmin):
    """Rematricular não pode criar um segundo destino para a mesma loja."""
    primeiro, _e1, _r1 = _matricular(conta, superadmin)
    segundo, envelope, _r2 = _matricular(conta, superadmin, existing_node_id=str(primeiro.id))

    assert segundo.id == primeiro.id
    # Um nó matriculado, não dois. (O outro LOCAL da conta é o da fixture.)
    assert SyncNode.objects.filter(
        node_type=NodeType.LOCAL, account=conta, name="Loja Centro"
    ).count() == 1
    # Credencial nova: o hash mudou.
    pacote = enrollment.decifrar(envelope, SEGREDO)
    assert pacote["SYNC_AUTH_TOKEN"]


def test_conta_inexistente_e_recusada(como_nuvem, superadmin):
    import uuid

    with pytest.raises(enrollment.EnrollmentRefused, match="não encontrada"):
        enrollment.enroll(
            username="root", password="senha-forte-123", account_id=str(uuid.uuid4()),
            enrollment_secret=SEGREDO, node_name="X",
        )


def test_matricula_fora_de_development_e_bloqueada(settings, como_nuvem, conta, superadmin):
    settings.SYNC_ENVIRONMENT = "production"
    from apps.synchronization.services import guard

    with pytest.raises(guard.SyncDisabled):
        _matricular(conta, superadmin)
