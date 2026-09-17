"""Métricas (§19.1) e a rede de segurança das triggers (§11.2)."""
import pytest
from django.contrib.auth import get_user_model
from django.db import connection
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import EventStatus
from apps.synchronization.models import SyncDirty, SyncEvent
from apps.synchronization.services import dirty, metrics, triggers

pytestmark = pytest.mark.django_db
User = get_user_model()


# ── Métricas ────────────────────────────────────────────────────────────────
def test_metricas_saem_no_formato_do_prometheus(como_nuvem, conta):
    Restaurant.objects.create(account=conta, legal_name="M LTDA", trade_name="M")
    texto = metrics.render()

    assert "# HELP sync_events_pending" in texto
    assert "# TYPE sync_events_pending gauge" in texto
    assert "sync_connections_active " in texto
    assert "sync_events_dead " in texto
    assert "sync_conflicts_open " in texto
    # Toda linha de amostra é "nome valor" — nada de linha pela metade.
    for linha in texto.strip().splitlines():
        if linha.startswith("#"):
            continue
        assert len(linha.rsplit(" ", 1)) == 2, linha


def test_atraso_cresce_com_evento_pendente_antigo(como_nuvem, conta):
    from django.utils import timezone

    Restaurant.objects.create(account=conta, legal_name="N LTDA", trade_name="N")
    SyncEvent.objects.update(created_at=timezone.now() - timezone.timedelta(hours=2))
    linhas = [linha for linha in metrics.coletar() if linha.startswith("sync_event_lag_seconds ")]
    assert linhas and float(linhas[0].split()[1]) > 7000


def test_metricas_sem_token_configurado_pedem_superusuario(como_nuvem, settings):
    settings.SYNC_METRICS_TOKEN = ""
    assert APIClient().get("/api/v1/sync/metrics/").status_code == 401


def test_metricas_com_token_de_raspagem(como_nuvem, settings):
    settings.SYNC_METRICS_TOKEN = "token-do-prometheus-bem-longo"
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Bearer token-do-prometheus-bem-longo")
    resposta = cliente.get("/api/v1/sync/metrics/")
    assert resposta.status_code == 200
    assert "text/plain" in resposta["Content-Type"]
    assert b"sync_events_pending" in resposta.content


def test_token_de_raspagem_errado_nao_entra(como_nuvem, settings):
    settings.SYNC_METRICS_TOKEN = "token-do-prometheus-bem-longo"
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION="Bearer chute")
    assert cliente.get("/api/v1/sync/metrics/").status_code == 401


def test_superusuario_ve_as_metricas(como_nuvem):
    raiz = User.objects.create_superuser("raiz2", "r2@t.test", "senha-forte-1234")
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(raiz).access_token}")
    assert cliente.get("/api/v1/sync/metrics/").status_code == 200


# ── Triggers / rede de segurança ────────────────────────────────────────────
@pytest.mark.skipif(
    connection.vendor == "postgresql",
    reason="Este teste é sobre o comportamento FORA do PostgreSQL.",
)
def test_no_sqlite_a_instalacao_nao_quebra(como_nuvem):
    """O dev roda SQLite; exigir PostgreSQL aqui só atrapalharia.

    A rede de segurança é uma garantia de produção. Na máquina de quem acabou
    de clonar o projeto ela simplesmente não existe, e dizer isso é melhor do
    que estourar.
    """
    assert triggers.is_postgres() is False
    assert triggers.install(log=lambda _m: None) == 0
    assert triggers.faltando() == []


def test_tabelas_sincronizadas_sao_as_do_catalogo(como_nuvem):
    tabelas = dict(triggers.tabelas_sincronizadas())
    assert "menu_product" in tabelas
    assert tabelas["menu_product"] == "product"
    # `auth_user` tem id sequencial: fica de fora, sem identidade global.
    assert "auth_user" not in tabelas


def test_marca_da_trigger_vira_evento(como_nuvem, conta):
    """Simula o que a trigger faria numa escrita em massa."""
    restaurante = Restaurant.objects.create(account=conta, legal_name="T LTDA", trade_name="T")
    SyncEvent.objects.all().delete()

    SyncDirty.objects.create(
        table_name=Restaurant._meta.db_table, row_id=str(restaurante.pk), operation="UPDATE"
    )
    convertidas, _ignoradas = dirty.process()

    assert convertidas == 1
    evento = SyncEvent.objects.get(entity_type="restaurant")
    assert evento.entity_id == str(restaurante.pk)
    assert evento.status == EventStatus.PENDING


def test_marca_ja_coberta_pelo_signal_nao_duplica(como_nuvem, conta):
    """Signal e trigger se sobrepõem — o que não pode é gerar dois eventos."""
    restaurante = Restaurant.objects.create(account=conta, legal_name="U LTDA", trade_name="U")
    antes = SyncEvent.objects.filter(entity_type="restaurant").count()

    marca = SyncDirty.objects.create(
        table_name=Restaurant._meta.db_table, row_id=str(restaurante.pk), operation="UPDATE"
    )
    SyncDirty.objects.filter(pk=marca.pk).update(
        changed_at=SyncEvent.objects.filter(entity_type="restaurant").first().created_at
    )
    dirty.process()

    assert SyncEvent.objects.filter(entity_type="restaurant").count() == antes


def test_marca_de_linha_apagada_nao_quebra(como_nuvem, conta):
    import uuid

    SyncDirty.objects.create(
        table_name=Restaurant._meta.db_table, row_id=str(uuid.uuid4()), operation="UPDATE"
    )
    convertidas, ignoradas = dirty.process()
    assert convertidas == 0 and ignoradas == 1
    assert SyncDirty.objects.get().error == "linha não existe mais"


def test_marca_de_tabela_fora_do_catalogo_e_ignorada(como_nuvem):
    import uuid

    SyncDirty.objects.create(table_name="django_session", row_id=str(uuid.uuid4()), operation="UPDATE")
    convertidas, ignoradas = dirty.process()
    assert convertidas == 0 and ignoradas == 1


def test_limpeza_so_apaga_marca_processada(como_nuvem):
    import uuid
    from django.utils import timezone

    antiga = SyncDirty.objects.create(table_name="x", row_id=str(uuid.uuid4()), operation="UPDATE")
    SyncDirty.objects.filter(pk=antiga.pk).update(
        processed_at=timezone.now() - timezone.timedelta(days=30)
    )
    pendente = SyncDirty.objects.create(table_name="y", row_id=str(uuid.uuid4()), operation="UPDATE")

    assert dirty.prune(dias=7) == 1
    assert SyncDirty.objects.filter(pk=pendente.pk).exists()
