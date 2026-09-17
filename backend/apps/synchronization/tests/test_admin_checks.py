"""Botões do Admin, checagens de configuração e matrícula automática.

Os botões do Admin disparam carga total e revogação — as duas ações mais caras
do sistema. Por isso o teste olha primeiro o que eles RECUSAM.
"""
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import NodeStatus, RunStatus, RunType
from apps.synchronization.models import SyncRun

pytestmark = pytest.mark.django_db
User = get_user_model()


@pytest.fixture
def admin_logado(db):
    User.objects.create_superuser("adminsync", "a@t.test", "senha-forte-1234")
    cliente = Client()
    cliente.login(username="adminsync", password="senha-forte-1234")
    return cliente


# ── Botões do Admin ─────────────────────────────────────────────────────────
def test_botao_de_carga_recusa_get(como_nuvem, admin_logado, no_loja):
    """GET dispararia uma carga total num pré-carregamento do navegador."""
    url = reverse("admin:synchronization_syncnode_bootstrap", args=[no_loja.id])
    assert admin_logado.get(url).status_code == 405


def test_botao_de_carga_enfileira(como_nuvem, admin_logado, conta, no_loja):
    Restaurant.objects.create(account=conta, legal_name="A LTDA", trade_name="A")
    url = reverse("admin:synchronization_syncnode_bootstrap", args=[no_loja.id])

    resposta = admin_logado.post(url, {"reason": "teste"})
    assert resposta.status_code == 302  # volta na hora para o Admin

    run = SyncRun.objects.get(target_node=no_loja)
    assert run.run_type == RunType.BOOTSTRAP
    assert run.reason == "teste"
    assert run.initiated_by.username == "adminsync"  # quem clicou fica registrado


def test_botao_de_carga_total_usa_run_type_full(como_nuvem, admin_logado, no_loja):
    url = reverse("admin:synchronization_syncnode_full", args=[no_loja.id])
    admin_logado.post(url, {})
    assert SyncRun.objects.get(target_node=no_loja).run_type == RunType.FULL


def test_duas_cargas_seguidas_avisam_em_vez_de_duplicar(como_nuvem, admin_logado, no_loja):
    url = reverse("admin:synchronization_syncnode_full", args=[no_loja.id])
    admin_logado.post(url, {})
    admin_logado.post(url, {})
    assert SyncRun.objects.filter(target_node=no_loja).count() == 1


def test_botao_de_revogar_mata_a_credencial(como_nuvem, admin_logado, no_loja):
    url = reverse("admin:synchronization_syncnode_revoke", args=[no_loja.id])
    admin_logado.post(url, {})

    no_loja.refresh_from_db()
    assert no_loja.status == NodeStatus.REVOKED
    assert no_loja.is_active is False
    assert no_loja.credential_hash == ""  # o token para de valer na hora


def test_revogar_nao_apaga_a_fila(como_nuvem, admin_logado, conta, no_loja):
    """Revogado por engano e reativado: tudo que ficou para trás continua lá."""
    from apps.synchronization.models import SyncEvent

    Restaurant.objects.create(account=conta, legal_name="B LTDA", trade_name="B")
    antes = SyncEvent.objects.count()

    admin_logado.post(reverse("admin:synchronization_syncnode_revoke", args=[no_loja.id]), {})
    assert SyncEvent.objects.count() == antes


def test_botao_de_testar_conexao_nao_muda_nada(como_nuvem, admin_logado, no_loja):
    url = reverse("admin:synchronization_syncnode_test", args=[no_loja.id])
    assert admin_logado.post(url, {}).status_code == 302
    no_loja.refresh_from_db()
    assert no_loja.status == NodeStatus.ACTIVE


def test_botao_de_reprocessar(como_nuvem, admin_logado, conta, no_loja):
    from apps.synchronization.constants import EventStatus
    from apps.synchronization.models import SyncEvent
    from apps.synchronization.services import retry

    Restaurant.objects.create(account=conta, legal_name="C LTDA", trade_name="C")
    evento = SyncEvent.objects.first()
    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "fora do ar")

    admin_logado.post(reverse("admin:synchronization_syncnode_retry", args=[no_loja.id]), {})
    evento.refresh_from_db()
    assert evento.status == EventStatus.PENDING


def test_usuario_sem_permissao_nao_inicia_carga(como_nuvem, conta, no_loja):
    """Staff sem a permissão específica vê o Admin mas não dispara carga."""
    usuario = User.objects.create_user("staff", "s@t.test", "senha-forte-1234", is_staff=True)
    from django.contrib.auth.models import Permission as DjangoPermission

    usuario.user_permissions.add(
        *DjangoPermission.objects.filter(content_type__app_label="synchronization")
        .exclude(codename="can_start_full_sync")
    )
    cliente = Client()
    cliente.login(username="staff", password="senha-forte-1234")

    cliente.post(reverse("admin:synchronization_syncnode_bootstrap", args=[no_loja.id]), {})
    assert not SyncRun.objects.filter(target_node=no_loja).exists()


def test_carga_fora_de_development_e_bloqueada(settings, como_nuvem, admin_logado, no_loja):
    settings.SYNC_ENVIRONMENT = "production"
    admin_logado.post(reverse("admin:synchronization_syncnode_full", args=[no_loja.id]), {})
    assert not SyncRun.objects.filter(target_node=no_loja).exists()


def test_change_form_mostra_os_botoes(como_nuvem, admin_logado, no_loja):
    url = reverse("admin:synchronization_syncnode_change", args=[no_loja.id])
    corpo = admin_logado.get(url).content.decode()

    assert "Sincronizar dados essenciais" in corpo
    assert "Sincronizar tudo" in corpo
    assert "Revogar vínculo" in corpo
    assert "csrfmiddlewaretoken" in corpo  # POST com CSRF, nunca link


def test_listagem_do_admin_abre(como_nuvem, admin_logado, conta, no_loja):
    Restaurant.objects.create(account=conta, legal_name="D LTDA", trade_name="D")
    for rota in ("syncnode", "syncevent", "syncrun", "syncconflict"):
        url = reverse(f"admin:synchronization_{rota}_changelist")
        assert admin_logado.get(url).status_code == 200, rota


# ── Checagens de configuração ───────────────────────────────────────────────
def test_check_silencioso_quando_desligado(settings, como_nuvem):
    from apps.synchronization.checks import check_sync_configuration

    settings.SYNC_ENABLED = False
    assert check_sync_configuration(None) == []


def test_check_avisa_ambiente_proibido(settings, como_nuvem):
    from apps.synchronization.checks import check_sync_configuration

    settings.SYNC_ENVIRONMENT = "production"
    ids = [a.id for a in check_sync_configuration(None)]
    assert "synchronization.W001" in ids


def test_check_avisa_node_type_invalido(settings, como_nuvem):
    from apps.synchronization.checks import check_sync_configuration

    settings.SYNC_NODE_TYPE = "servidor"
    ids = [a.id for a in check_sync_configuration(None)]
    assert "synchronization.W002" in ids


def test_check_avisa_loja_sem_credencial(settings, como_loja):
    from apps.synchronization.checks import check_sync_configuration

    settings.SYNC_AUTH_TOKEN = ""
    settings.SYNC_CLOUD_WSS_URL = ""
    avisos = {a.id: a for a in check_sync_configuration(None)}
    assert "synchronization.W003" in avisos
    # O aviso precisa dizer que a loja CONTINUA operando.
    assert "continua operando" in avisos["synchronization.W003"].hint


def test_check_nao_reclama_de_loja_configurada(como_loja):
    from apps.synchronization.checks import check_sync_configuration

    ids = [a.id for a in check_sync_configuration(None)]
    assert "synchronization.W003" not in ids


# ── Matrícula automática ────────────────────────────────────────────────────
def test_autostart_silencioso_quando_ja_matriculado(como_loja):
    from apps.synchronization.services import autostart

    assert autostart.ensure_enrolled(log=lambda _m: None) == (False, "")


def test_autostart_desligado_explica_o_caminho_manual(settings, como_loja):
    from apps.synchronization.services import autostart

    settings.SYNC_AUTH_TOKEN = ""
    settings.SYNC_AUTO_ENROLL = False
    matriculou, aviso = autostart.ensure_enrolled(log=lambda _m: None)
    assert matriculou is False
    assert "sync_enroll" in aviso


def test_autostart_ligado_sem_dados_diz_o_que_falta(settings, como_loja):
    from apps.synchronization.services import autostart

    settings.SYNC_AUTH_TOKEN = ""
    settings.SYNC_AUTO_ENROLL = True
    settings.SYNC_CLOUD_API_URL = ""
    matriculou, aviso = autostart.ensure_enrolled(log=lambda _m: None)
    assert matriculou is False
    assert "SYNC_CLOUD_API_URL" in aviso


def test_autostart_com_nuvem_fora_do_ar_adia_sem_quebrar(settings, como_loja, monkeypatch):
    """Nuvem indisponível na primeira subida é esperado, não é erro."""
    from apps.synchronization.services import autostart, enrollment_client

    settings.SYNC_AUTH_TOKEN = ""
    settings.SYNC_AUTO_ENROLL = True
    settings.SYNC_CLOUD_API_URL = "https://nuvem.invalida"
    settings.SYNC_ENROLL_USERNAME = "x"
    settings.SYNC_ENROLL_PASSWORD = "y"
    settings.SYNC_ACCOUNT_ID = "00000000-0000-0000-0000-000000000000"
    settings.SYNC_ENROLL_SECRET = "s" * 30

    def recusa(**_kwargs):
        raise enrollment_client.EnrollmentError("sem rota para a nuvem")

    monkeypatch.setattr(enrollment_client, "request_package", recusa)
    matriculou, aviso = autostart.ensure_enrolled(log=lambda _m: None)
    assert matriculou is False
    assert "adiada" in aviso


def test_run_em_andamento_bloqueia_outra_pela_api(como_nuvem, no_loja):
    from apps.synchronization.services import bootstrap

    run = bootstrap.start_run(target_node=no_loja)
    assert run.is_busy
    assert run.status in RunStatus.BUSY
