"""Os comandos de terminal: é por eles que alguém conserta a loja às 22h.

Um comando que estoura com traceback em vez de dizer o que falta custa a noite
de quem está no suporte — daí testar a mensagem, não só o caminho feliz.
"""
import io
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.restaurants.models import Restaurant
from apps.synchronization.constants import EventStatus, NodeType
from apps.synchronization.models import SyncEvent, SyncNode
from apps.synchronization.services import retry

pytestmark = pytest.mark.django_db


def _rodar(comando, *args, **kwargs):
    saida = io.StringIO()
    call_command(comando, *args, stdout=saida, stderr=saida, **kwargs)
    return saida.getvalue()


# ── sync_check_registry ─────────────────────────────────────────────────────
def test_registry_aprova_quando_todo_model_tem_decisao(como_nuvem):
    texto = _rodar("sync_check_registry", "--quiet")
    assert "OK:" in texto and "sincronizados" in texto


def test_registry_lista_entidades_e_exclusoes(como_nuvem):
    texto = _rodar("sync_check_registry")
    assert "Sincronizados (ordem de carga)" in texto
    assert "Excluídos:" in texto
    assert "product" in texto


def test_registry_reprova_model_sem_decisao(como_nuvem, monkeypatch):
    """A proteção que existe para o model que alguém criar amanhã.

    O patch é no MÓDULO DO COMANDO, não em `decisions`: o comando faz
    `from ... import EXCLUDED`, que copia o nome na importação — trocar o
    atributo original depois disso não muda nada.
    """
    from apps.synchronization.management.commands import sync_check_registry as cmd

    sem_uma = {k: v for k, v in cmd.EXCLUDED.items() if k != "accounts.Plan"}
    monkeypatch.setattr(cmd, "EXCLUDED", sem_uma)

    with pytest.raises(CommandError, match="sem decisão de sincronização"):
        _rodar("sync_check_registry", "--quiet")


# ── sync_status ─────────────────────────────────────────────────────────────
def test_status_mostra_configuracao_nos_e_fila(como_nuvem, conta, no_loja):
    Restaurant.objects.create(account=conta, legal_name="S LTDA", trade_name="S")
    texto = _rodar("sync_status")

    assert "SYNC_ENABLED" in texto
    assert "Nós" in texto and no_loja.name in texto
    assert "Fila" in texto and "a enviar" in texto


def test_status_quiet_nao_imprime_relatorio(como_nuvem):
    assert _rodar("sync_status", "--quiet").strip() == ""


def test_status_sem_no_cadastrado_diz_isso(como_nuvem):
    SyncNode.objects.all().delete()
    assert "nenhum nó cadastrado" in _rodar("sync_status")


# ── sync_recover ────────────────────────────────────────────────────────────
def test_recover_exige_uma_acao(como_nuvem):
    with pytest.raises(CommandError, match="Escolha uma ação"):
        _rodar("sync_recover")


def test_recover_devolve_mortos_a_fila(como_nuvem, conta, no_loja):
    Restaurant.objects.create(account=conta, legal_name="R LTDA", trade_name="R")
    evento = SyncEvent.objects.first()
    for _ in range(retry.MAX_TENTATIVAS):
        retry.mark_failure(evento, "nuvem fora")
    evento.refresh_from_db()
    assert evento.status == EventStatus.DEAD

    texto = _rodar("sync_recover", "--requeue")
    assert "devolvidos à fila" in texto
    evento.refresh_from_db()
    assert evento.status == EventStatus.PENDING


def test_recover_exporta_a_fila_em_json(como_nuvem, conta, no_loja, tmp_path):
    Restaurant.objects.create(account=conta, legal_name="X LTDA", trade_name="X")
    destino = tmp_path / "fila.json"

    texto = _rodar("sync_recover", "--export", str(destino))
    assert "exportados" in texto

    dados = json.loads(destino.read_text(encoding="utf-8"))
    assert dados and "payload" in dados[0] and "event_id" in dados[0]


def test_recover_com_event_id_inexistente_avisa(como_nuvem):
    import uuid

    with pytest.raises(CommandError, match="não encontrado"):
        _rodar("sync_recover", "--requeue", "--event-id", str(uuid.uuid4()))


def test_recover_prune_so_apaga_confirmado(como_nuvem, conta, no_loja):
    from django.utils import timezone

    Restaurant.objects.create(account=conta, legal_name="P LTDA", trade_name="P")
    total = SyncEvent.objects.count()
    SyncEvent.objects.update(
        status=EventStatus.ACKNOWLEDGED,
        acknowledged_at=timezone.now() - timezone.timedelta(days=400),
    )
    texto = _rodar("sync_recover", "--prune-days", "30")
    assert f"{total} evento(s)" in texto
    assert SyncEvent.objects.count() == 0


# ── sync_install_triggers ───────────────────────────────────────────────────
def test_triggers_fora_do_postgres_avisa_sem_quebrar(como_nuvem):
    from apps.synchronization.services import triggers

    if triggers.is_postgres():
        pytest.skip("Este teste cobre o comportamento fora do PostgreSQL.")
    texto = _rodar("sync_install_triggers")
    assert "não é PostgreSQL" in texto


def test_triggers_nao_instalam_com_sync_desligado(settings, como_nuvem):
    """A guarda que torna seguro deixar o comando no boot de PRODUÇÃO.

    O `docker-compose.yml` da raiz roda este comando em todo boot. Com a
    sincronização desligada — que é como a produção sobe hoje — instalar as
    triggers gravaria uma marca em `synchronization_syncdirty` a cada escrita
    de toda tabela sincronizada, que ninguém consumiria: uma tabela crescendo
    sozinha para nada.
    """
    from apps.synchronization.services import triggers

    if not triggers.is_postgres():
        pytest.skip("As triggers só existem no PostgreSQL.")

    settings.SYNC_ENABLED = False
    triggers.uninstall(log=lambda _m: None)

    texto = _rodar("sync_install_triggers")
    assert "NÃO instaladas" in texto
    assert triggers.installed() == set()

    # E com --force instala assim mesmo, para quem sabe o que quer.
    _rodar("sync_install_triggers", "--force")
    assert triggers.installed()
    triggers.uninstall(log=lambda _m: None)


# ── sync_provision_node ─────────────────────────────────────────────────────
def test_provision_exige_no_cloud(como_loja, conta):
    """No nó LOCAL o comando não faz sentido e diz por quê."""
    with pytest.raises(CommandError, match="nó CLOUD"):
        _rodar("sync_provision_node", "--account", str(conta.id),
               "--name", "X", "--cloud-url", "wss://x/ws/sync/v1/")


def test_provision_conta_inexistente(como_nuvem):
    with pytest.raises(CommandError, match="Conta não encontrada"):
        _rodar("sync_provision_node", "--account", "nao-existe",
               "--name", "X", "--cloud-url", "wss://x/ws/sync/v1/")


def test_provision_gera_pacote_e_grava_env(como_nuvem, conta, tmp_path):
    destino = tmp_path / "loja.env"
    texto = _rodar("sync_provision_node", "--account", str(conta.id), "--name", "Loja Nova",
                   "--cloud-url", "wss://n.test/ws/sync/v1/", "--env-file", str(destino))

    assert "cadastrado" in texto and "NÃO poderão ser recuperados" in texto
    conteudo = destino.read_text(encoding="utf-8")
    assert "SYNC_AUTH_TOKEN=" in conteudo and "SYNC_ENCRYPTION_KEY=" in conteudo
    assert SyncNode.objects.filter(name="Loja Nova", node_type=NodeType.LOCAL).exists()


# ── sync_install_node ───────────────────────────────────────────────────────
def test_install_node_exige_no_local(como_nuvem):
    with pytest.raises(CommandError, match="nó LOCAL"):
        _rodar("sync_install_node")


def test_install_node_sem_variaveis_avisa(settings, como_loja):
    settings.SYNC_NODE_ID = ""
    settings.SYNC_PAIR_ID = ""
    settings.SYNC_ACCOUNT_ID = ""
    with pytest.raises(CommandError, match="Faltam SYNC_NODE_ID"):
        _rodar("sync_install_node")


# ── sync_worker ─────────────────────────────────────────────────────────────
def test_worker_recusa_rodar_na_nuvem(como_nuvem):
    with pytest.raises(CommandError, match="só roda no nó LOCAL"):
        _rodar("sync_worker", "--once")


def test_worker_desligado_recusa(settings, como_loja):
    settings.SYNC_ENABLED = False
    with pytest.raises(CommandError, match="não está ligada"):
        _rodar("sync_worker", "--once")


def test_worker_sem_credencial_explica_em_vez_de_estourar(settings, como_loja):
    """A mensagem é o produto aqui: quem lê está tentando subir uma loja."""
    settings.SYNC_AUTH_TOKEN = ""
    settings.SYNC_CLOUD_WSS_URL = ""
    with pytest.raises(CommandError) as erro:
        _rodar("sync_worker", "--once")
    assert "sync_enroll" in str(erro.value) or "SYNC_CLOUD_WSS_URL" in str(erro.value)


# ── sync_enroll ─────────────────────────────────────────────────────────────
def test_enroll_exige_no_local(como_nuvem):
    with pytest.raises(CommandError, match="nó LOCAL"):
        _rodar("sync_enroll", "--api-url", "https://n.test", "--username", "x",
               "--password", "y", "--account", "z", "--secret", "s" * 30)


def test_enroll_ja_matriculado_pede_force(settings, como_loja):
    settings.SYNC_AUTH_TOKEN = "ja-tenho-token"
    texto = _rodar("sync_enroll", "--api-url", "https://n.test", "--username", "x",
                   "--password", "y", "--account", "z", "--secret", "s" * 30)
    assert "--force" in texto


# ── Persistência da matrícula ───────────────────────────────────────────────
def test_credenciais_da_matricula_sobrevivem_ao_restart(tmp_path, settings):
    """O arquivo gravado pela matrícula precisa ser LIDO de volta.

    Gravar não bastava: nada o lia. Todo restart do container reencontrava
    `SYNC_AUTH_TOKEN` vazio, concluía "não estou matriculado" e se matriculava
    de novo — gastando uma das 5 tentativas por hora, rotacionando a credencial
    e disparando outra carga total. Um `docker compose restart` custava isso.
    """
    import importlib

    destino = tmp_path / "credentials.env"
    destino.write_text(
        "SYNC_NODE_ID=11111111-1111-1111-1111-111111111111\n"
        "SYNC_AUTH_TOKEN=token-vindo-da-matricula\n"
        "SYNC_ENCRYPTION_KEY=chave-do-ambiente\n",
        encoding="utf-8",
    )

    import os

    anterior = os.environ.get("SYNC_ENROLL_ENV_PATH")
    os.environ["SYNC_ENROLL_ENV_PATH"] = str(destino)
    try:
        from config.settings import sync as modulo

        importlib.reload(modulo)
        assert modulo.SYNC_AUTH_TOKEN == "token-vindo-da-matricula"
        assert modulo.SYNC_NODE_ID == "11111111-1111-1111-1111-111111111111"
    finally:
        if anterior is None:
            os.environ.pop("SYNC_ENROLL_ENV_PATH", None)
        else:
            os.environ["SYNC_ENROLL_ENV_PATH"] = anterior
        importlib.reload(modulo)


def test_o_ambiente_explicito_vence_o_arquivo(tmp_path):
    """Quem provisionou à mão não pode ser sobrescrito por matrícula antiga."""
    import importlib
    import os

    destino = tmp_path / "credentials.env"
    destino.write_text("SYNC_AUTH_TOKEN=token-do-arquivo\n", encoding="utf-8")

    guardados = {k: os.environ.get(k) for k in ("SYNC_ENROLL_ENV_PATH", "SYNC_AUTH_TOKEN")}
    os.environ["SYNC_ENROLL_ENV_PATH"] = str(destino)
    os.environ["SYNC_AUTH_TOKEN"] = "token-colado-na-mao"
    try:
        from config.settings import sync as modulo

        importlib.reload(modulo)
        assert modulo.SYNC_AUTH_TOKEN == "token-colado-na-mao"
    finally:
        for k, v in guardados.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        importlib.reload(modulo)
