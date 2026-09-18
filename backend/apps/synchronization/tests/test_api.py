"""A API de gerenciamento: quem pode o quê, e o que ela nunca devolve."""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import UserProfile
from apps.accounts.role_catalog import ensure_system_roles
from apps.synchronization.services import enrollment

pytestmark = pytest.mark.django_db
User = get_user_model()


def _cliente(usuario):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(usuario).access_token}")
    return cliente


@pytest.fixture
def admin(db, conta):
    usuario = User.objects.create_user("adm", "adm@t.test", "senha-forte-123")
    UserProfile.objects.create(account=conta, user=usuario, role=ensure_system_roles(conta)["admin"])
    return usuario


@pytest.fixture
def garcom(db, conta):
    usuario = User.objects.create_user("gar", "gar@t.test", "senha-forte-123")
    UserProfile.objects.create(account=conta, user=usuario, role=ensure_system_roles(conta)["waiter"])
    return usuario


@pytest.fixture
def admin_vizinho(db, outra_conta):
    usuario = User.objects.create_user("adm2", "adm2@t.test", "senha-forte-123")
    UserProfile.objects.create(
        account=outra_conta, user=usuario, role=ensure_system_roles(outra_conta)["admin"]
    )
    return usuario


def test_admin_lista_os_nos_da_propria_conta(como_nuvem, admin, no_loja):
    resposta = _cliente(admin).get("/api/v1/sync/nodes/")
    assert resposta.status_code == 200
    ids = {item["id"] for item in resposta.json()["results"]}
    assert str(no_loja.id) in ids


def test_admin_de_outra_conta_nao_ve_nada(como_nuvem, admin_vizinho, no_loja):
    resposta = _cliente(admin_vizinho).get("/api/v1/sync/nodes/")
    assert resposta.status_code == 200
    ids = {item["id"] for item in resposta.json()["results"]}
    assert str(no_loja.id) not in ids


def test_garcom_nao_acessa_o_gerenciamento(como_nuvem, garcom):
    assert _cliente(garcom).get("/api/v1/sync/nodes/").status_code == 403


def test_sem_autenticacao_e_401(como_nuvem):
    assert APIClient().get("/api/v1/sync/nodes/").status_code == 401


def test_a_listagem_nunca_devolve_segredo(como_nuvem, admin, no_loja):
    corpo = _cliente(admin).get("/api/v1/sync/nodes/").json()
    texto = str(corpo)
    assert "credential_hash" not in texto
    assert "SYNC_AUTH_TOKEN" not in texto
    assert "encryption_key" not in texto.lower() or "encryption_key_id" in texto.lower()


def test_status_mostra_a_fila(como_nuvem, admin):
    corpo = _cliente(admin).get("/api/v1/sync/nodes/status/").json()
    assert corpo["enabled"] is True
    assert corpo["environment"] == "development"
    assert "queue" in corpo and "mortos" in corpo["queue"]


def test_matricula_com_credencial_errada_da_403(como_nuvem, conta):
    resposta = APIClient().post("/api/v1/sync/enroll/", {
        "username": "ninguem", "password": "chute",
        "account_id": str(conta.id),
        "enrollment_secret": "segredo-de-matricula-com-24-mais",
        "node_name": "Invasor",
    }, format="json")
    assert resposta.status_code == 403
    assert "package" not in resposta.json()


def test_matricula_com_segredo_curto_da_400(como_nuvem, conta):
    resposta = APIClient().post("/api/v1/sync/enroll/", {
        "username": "x", "password": "y", "account_id": str(conta.id),
        "enrollment_secret": "curto", "node_name": "X",
    }, format="json")
    assert resposta.status_code == 400


def test_matricula_valida_devolve_pacote_cifrado(como_nuvem, conta, settings):
    settings.REST_FRAMEWORK = {**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {
        **settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"], "sync_enroll": "100/min"}}
    User.objects.create_superuser("raiz", "raiz@t.test", "senha-forte-1234")
    segredo = "segredo-de-matricula-com-24-mais"

    resposta = APIClient().post("/api/v1/sync/enroll/", {
        "username": "raiz", "password": "senha-forte-1234",
        "account_id": str(conta.id), "enrollment_secret": segredo,
        "node_name": "Loja API", "cloud_wss_url": "wss://n.test/ws/sync/v1/",
    }, format="json")

    assert resposta.status_code == 201
    corpo = resposta.json()
    assert "ciphertext" in corpo["package"]
    assert "SYNC_AUTH_TOKEN" not in str(corpo["package"])
    pacote = enrollment.decifrar(corpo["package"], segredo)
    assert pacote["SYNC_AUTH_TOKEN"] and pacote["SYNC_NODE_ID"] == corpo["node_id"]
    assert corpo["run_type"] == "FULL"


# ── Ações que mexem ─────────────────────────────────────────────────────────
def test_admin_dispara_carga_pela_api(como_nuvem, admin, no_loja):
    resposta = _cliente(admin).post(
        f"/api/v1/sync/nodes/{no_loja.id}/start_run/", {"run_type": "FULL"}, format="json"
    )
    assert resposta.status_code == 202
    assert resposta.json()["run_type"] == "FULL"


def test_segunda_carga_no_mesmo_no_da_409(como_nuvem, admin, no_loja):
    url = f"/api/v1/sync/nodes/{no_loja.id}/start_run/"
    _cliente(admin).post(url, {}, format="json")
    assert _cliente(admin).post(url, {}, format="json").status_code == 409


def test_carga_fora_de_development_da_503(settings, como_nuvem, admin, no_loja):
    # `production` virou um ambiente VÁLIDO; o que estes testes exercitam é
    # o valor desconhecido, que continua sendo recusado.
    settings.SYNC_ENVIRONMENT = "homologacao-do-fulano"
    resposta = _cliente(admin).post(
        f"/api/v1/sync/nodes/{no_loja.id}/start_run/", {}, format="json"
    )
    assert resposta.status_code == 503


def test_garcom_nao_dispara_carga(como_nuvem, garcom, no_loja):
    resposta = _cliente(garcom).post(
        f"/api/v1/sync/nodes/{no_loja.id}/start_run/", {}, format="json"
    )
    assert resposta.status_code == 403


def test_revogar_pela_api(como_nuvem, admin, no_loja):
    from apps.synchronization.constants import NodeStatus

    resposta = _cliente(admin).post(f"/api/v1/sync/nodes/{no_loja.id}/revoke/", {}, format="json")
    assert resposta.status_code == 200
    no_loja.refresh_from_db()
    assert no_loja.status == NodeStatus.REVOKED


def test_rotacionar_credencial_mostra_uma_vez(como_nuvem, admin, no_loja):
    anterior = no_loja.credential_hash
    resposta = _cliente(admin).post(
        f"/api/v1/sync/nodes/{no_loja.id}/rotate_credentials/", {}, format="json"
    )
    assert resposta.status_code == 200
    pacote = resposta.json()["package"]
    assert pacote["SYNC_AUTH_TOKEN"] and pacote["SYNC_ENCRYPTION_KEY"]
    assert "não é possível recuperar" in resposta.json()["warning"]

    no_loja.refresh_from_db()
    assert no_loja.credential_hash != anterior  # a anterior parou de valer


def test_reprocessar_pela_api(como_nuvem, admin, conta, no_loja):
    from apps.restaurants.models import Restaurant
    from apps.synchronization.constants import EventStatus
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import retry

    Restaurant.objects.create(account=conta, legal_name="API LTDA", trade_name="API")
    evento = SyncEvent.objects.first()
    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "fora")

    resposta = _cliente(admin).post(f"/api/v1/sync/nodes/{no_loja.id}/requeue/", {}, format="json")
    assert resposta.status_code == 200
    assert resposta.json()["requeued"] >= 1
    evento.refresh_from_db()
    assert evento.status == EventStatus.PENDING


def test_evento_individual_volta_para_a_fila(como_nuvem, admin, conta, no_loja):
    from apps.restaurants.models import Restaurant
    from apps.synchronization.constants import EventStatus
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import retry

    Restaurant.objects.create(account=conta, legal_name="EV LTDA", trade_name="EV")
    evento = SyncEvent.objects.first()
    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "fora")

    resposta = _cliente(admin).post(f"/api/v1/sync/events/{evento.id}/requeue/", {}, format="json")
    assert resposta.status_code == 200
    evento.refresh_from_db()
    assert evento.status == EventStatus.PENDING


def test_lista_de_mortos_e_parados(como_nuvem, admin, conta, no_loja):
    from apps.restaurants.models import Restaurant
    from apps.synchronization.services import retry
    from apps.synchronization.models import SyncEvent

    Restaurant.objects.create(account=conta, legal_name="M LTDA", trade_name="M")
    evento = SyncEvent.objects.first()
    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "fora")

    mortos = _cliente(admin).get("/api/v1/sync/events/dead/")
    assert mortos.status_code == 200 and len(mortos.json()) >= 1
    assert _cliente(admin).get("/api/v1/sync/events/stuck/?minutes=0").status_code == 200


def test_conflito_resolvido_registra_quem_decidiu(como_nuvem, admin, conta, no_loja, no_nuvem):
    from apps.synchronization.constants import ConflictStatus
    from apps.synchronization.models import SyncConflict

    conflito = SyncConflict.objects.create(
        account=conta, entity_type="invoice", entity_id="x",
        source_node=no_loja, target_node=no_nuvem,
        local_version=1, remote_version=2,
    )
    resposta = _cliente(admin).post(
        f"/api/v1/sync/conflicts/{conflito.id}/resolve/",
        {"status": ConflictStatus.RESOLVED, "notes": "a nuvem estava certa"}, format="json",
    )
    assert resposta.status_code == 200
    conflito.refresh_from_db()
    assert conflito.status == ConflictStatus.RESOLVED
    assert conflito.resolved_by == admin
    assert conflito.resolved_at is not None


def test_cargas_e_conflitos_sao_somente_leitura(como_nuvem, admin):
    assert _cliente(admin).post("/api/v1/sync/runs/", {}, format="json").status_code == 405
    assert _cliente(admin).post("/api/v1/sync/conflicts/", {}, format="json").status_code == 405


def test_permissao_do_catalogo_libera_quem_nao_e_admin(como_nuvem, conta, garcom, no_loja):
    """O gate usa o catálogo do projeto, não o `auth_permission` do Django."""
    from apps.accounts.models import Permission

    permissao = Permission.objects.get(code="sync.manage")
    garcom.profile.specific_permissions.add(permissao)

    resposta = _cliente(garcom).post(
        f"/api/v1/sync/nodes/{no_loja.id}/start_run/", {}, format="json"
    )
    assert resposta.status_code == 202


def test_so_ver_nao_deixa_disparar_carga(como_nuvem, conta, garcom, no_loja):
    from apps.accounts.models import Permission

    garcom.profile.specific_permissions.add(Permission.objects.get(code="sync.view"))

    assert _cliente(garcom).get("/api/v1/sync/nodes/").status_code == 200
    assert _cliente(garcom).post(
        f"/api/v1/sync/nodes/{no_loja.id}/start_run/", {}, format="json"
    ).status_code == 403
