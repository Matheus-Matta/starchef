"""Matrícula automática quando o backend da loja sobe pela primeira vez.

O `sync_worker` chama isto antes de tentar conectar. Se a instalação ainda não
tem credencial e o `.env.local` traz usuário, senha, conta e segredo de
matrícula, ele se matricula sozinho e a nuvem já enfileira a carga total.

Duas regras que não mudam:

1. **Falhar aqui nunca impede o backend de operar.** Sem nuvem alcançável, a
   loja continua vendendo; a matrícula é tentada de novo no próximo ciclo.
2. **A automação não relaxa a autenticação.** As mesmas credenciais, o mesmo
   segredo, a mesma cifra. Automático só quer dizer "sem alguém digitando".
"""
import logging

from django.conf import settings

from apps.synchronization.services import enrollment_client, guard

logger = logging.getLogger(__name__)


def configuracao_disponivel():
    """O `.env.local` tem o necessário para uma matrícula sem interação?"""
    return all([
        getattr(settings, "SYNC_CLOUD_API_URL", ""),
        getattr(settings, "SYNC_ENROLL_USERNAME", ""),
        getattr(settings, "SYNC_ENROLL_PASSWORD", ""),
        getattr(settings, "SYNC_ACCOUNT_ID", ""),
        getattr(settings, "SYNC_ENROLL_SECRET", ""),
    ])


def ensure_enrolled(*, log=logger.info):
    """Garante identidade local. Devolve `(matriculou, mensagem)`.

    `matriculou=False` com mensagem vazia significa "já estava matriculado" —
    o caminho normal a partir do segundo boot.
    """
    if not guard.is_enabled():
        return False, ""

    if enrollment_client.already_enrolled():
        return False, ""

    if not getattr(settings, "SYNC_AUTO_ENROLL", False):
        return False, (
            "Sem credencial e SYNC_AUTO_ENROLL desligado. "
            "Rode `manage.py sync_enroll` para matricular esta loja."
        )

    if not configuracao_disponivel():
        return False, (
            "Matrícula automática ligada, mas faltam SYNC_CLOUD_API_URL, "
            "SYNC_ENROLL_USERNAME, SYNC_ENROLL_PASSWORD, SYNC_ACCOUNT_ID ou "
            "SYNC_ENROLL_SECRET no .env.local."
        )

    return _matricular(log)


def _matricular(log):
    from apps.synchronization.constants import NodeType
    from apps.synchronization.models import SyncNode

    existente = SyncNode.objects.filter(is_self=True, node_type=NodeType.LOCAL).first()
    log("sync: sem credencial local — matriculando na nuvem…")
    try:
        pacote = enrollment_client.request_package(
            api_url=settings.SYNC_CLOUD_API_URL,
            username=settings.SYNC_ENROLL_USERNAME,
            password=settings.SYNC_ENROLL_PASSWORD,
            account_id=settings.SYNC_ACCOUNT_ID,
            secret=settings.SYNC_ENROLL_SECRET,
            node_name=getattr(settings, "SYNC_NODE_NAME", "") or "Servidor da loja",
            restaurant_id=getattr(settings, "SYNC_STORE_ID", "") or None,
            cloud_wss_url=getattr(settings, "SYNC_CLOUD_WSS_URL", ""),
            existing_node_id=str(existente.id) if existente else None,
        )
    except enrollment_client.EnrollmentError as erro:
        # Nuvem fora do ar na primeira subida é um cenário esperado, não um
        # crash: o worker tenta de novo no próximo ciclo de reconexão.
        logger.warning("sync: matrícula adiada — %s", erro)
        return False, f"Matrícula adiada: {erro}"

    proprio = enrollment_client.install(
        pacote, env_path=getattr(settings, "SYNC_ENROLL_ENV_PATH", "") or None
    )
    run_id = pacote.get("SYNC_INITIAL_RUN_ID", "")
    mensagem = f"Matriculado: nó {proprio.id}."
    if run_id:
        mensagem += f" A nuvem enfileirou a carga total {run_id}."
    log(f"sync: {mensagem}")
    return True, mensagem
