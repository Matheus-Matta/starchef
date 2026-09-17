"""Avisos de configuração da sincronização no `manage.py check`.

São Warnings, nunca Errors: um erro aqui impediria o backend de subir, e o
princípio é o oposto — sincronização mal configurada degrada a sincronização,
não tira a loja do ar.
"""
from django.conf import settings
from django.core.checks import Warning as CheckWarning
from django.core.checks import register

from apps.synchronization.constants import NodeType
from apps.synchronization.services import guard


@register("synchronization")
def check_sync_configuration(app_configs, **kwargs):
    if not guard.is_enabled():
        return []

    avisos = []
    if not guard.environment_is_allowed():
        avisos.append(CheckWarning(
            f"SYNC_ENVIRONMENT={guard.current_environment() or '(vazio)'}: {guard.MENSAGEM}",
            hint="Nesta fase só `development` é aceito. O worker vai recusar subir.",
            id="synchronization.W001",
        ))

    tipo = guard.node_type()
    if tipo not in (NodeType.LOCAL, NodeType.CLOUD):
        avisos.append(CheckWarning(
            f"SYNC_NODE_TYPE inválido: {tipo or '(vazio)'}.",
            hint="Use `local` (servidor da loja) ou `cloud` (servidor central).",
            id="synchronization.W002",
        ))

    if tipo == NodeType.LOCAL:
        avisos.extend(_checar_local())
    avisos.extend(_checar_triggers())
    return avisos


def _checar_triggers():
    """A rede de segurança do §11.2 está instalada neste PostgreSQL?

    Sem ela o sistema funciona — e é justamente esse o problema: escrita em
    massa (`QuerySet.update`, `bulk_create`, SQL direto) deixa de virar evento
    sem barulho nenhum, e a divergência só aparece quando alguém compara os
    dois bancos.
    """
    try:
        from apps.synchronization.services import triggers

        if not triggers.is_postgres():
            return []
        ausentes = triggers.faltando()
    except Exception:  # noqa: BLE001 — banco ainda migrando, por exemplo
        return []

    if not ausentes:
        return []
    return [CheckWarning(
        f"{len(ausentes)} tabela(s) sincronizada(s) sem trigger de captura.",
        hint=(
            "Rode `manage.py sync_install_triggers`. Sem elas, escrita em massa "
            "(QuerySet.update, bulk_create, SQL direto) não vira evento. "
            "Tabelas: " + ", ".join(ausentes[:8]) + ("…" if len(ausentes) > 8 else "")
        ),
        id="synchronization.W004",
    )]


def _checar_local():
    faltando = [
        nome for nome in ("SYNC_NODE_ID", "SYNC_CLOUD_WSS_URL", "SYNC_AUTH_TOKEN")
        if not getattr(settings, nome, "")
    ]
    if not faltando:
        return []
    return [CheckWarning(
        "Nó LOCAL sem credencial: " + ", ".join(faltando),
        hint=(
            "A loja continua operando e gravando eventos na outbox; eles ficam "
            "guardados até alguém rodar `manage.py sync_install_node` com o "
            "pacote gerado na nuvem."
        ),
        id="synchronization.W003",
    )]
