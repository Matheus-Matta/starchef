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
            hint="Use `development` ou `production` — um typo como `prod` não vira ambiente novo, vira nó que não conecta em lugar nenhum.",
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
    avisos.extend(_checar_chave())
    avisos.extend(_checar_triggers())
    return avisos


def _checar_chave():
    """A chave AES é utilizável?

    Sem esta checagem o erro aparece no pior lugar possível: a conexão é
    aceita, o HELLO é autenticado, e a instalação estoura ao CIFRAR a
    resposta. Do outro lado se vê uma conexão que cai sozinha, sem mensagem —
    e o motivo real (uma chave com o número errado de bytes) não aparece em
    lugar nenhum.

    O engano comum é usar `secrets.token_urlsafe(32)`, que devolve ~43
    caracteres e decodifica para 32 bytes só por acaso, ou `token_urlsafe(48)`,
    que dá 48 bytes e é recusado. O certo é
    `base64.b64encode(secrets.token_bytes(32))`.
    """
    from apps.synchronization.services import crypto

    chave = getattr(settings, "SYNC_ENCRYPTION_KEY", "")
    if not chave:
        # Vazio é um modo válido (WSS sem AES-GCM adicional), desde que as
        # DUAS pontas estejam assim.
        return []
    try:
        crypto.load_key(chave)
    except Exception as erro:  # noqa: BLE001 — a mensagem é o produto aqui
        return [CheckWarning(
            f"SYNC_ENCRYPTION_KEY inválida: {erro}",
            hint=(
                "Gere com: python -c \"import secrets,base64;"
                "print(base64.b64encode(secrets.token_bytes(32)).decode())\" — "
                "e use a MESMA nas duas pontas. Com ela assim, a conexão é "
                "aceita e a instalação estoura ao cifrar a resposta."
            ),
            id="synchronization.W005",
        )]
    return []


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


def _checar_nome():
    """Esta loja tem nome próprio?

    Vazio cai no padrão "Servidor da loja", e o padrão é o mesmo para todo
    mundo: com três lojas matriculadas, o Admin da nuvem lista três nós com o
    mesmo nome e nada que os distinga além do UUID. Quem for descartar a fila
    de uma delas está a um clique de descartar a da outra.
    """
    if not getattr(settings, "SYNC_AUTO_ENROLL", False):
        return []
    if getattr(settings, "SYNC_NODE_NAME", "").strip():
        return []
    return [CheckWarning(
        "SYNC_NODE_NAME vazio: esta loja vai se matricular como "
        '"Servidor da loja".',
        hint=(
            "Dê um nome próprio (ex.: SYNC_NODE_NAME=Loja Cobogó). É como ela "
            "aparece no Admin da nuvem; sem isso, todas ficam com o mesmo nome "
            "e só o UUID as distingue. Trocar depois e rematricular renomeia o "
            "nó existente."
        ),
        id="synchronization.W006",
    )]


def _checar_local():
    avisos = _checar_nome()
    faltando = [
        nome for nome in ("SYNC_NODE_ID", "SYNC_CLOUD_WSS_URL", "SYNC_AUTH_TOKEN")
        if not getattr(settings, nome, "")
    ]
    if not faltando:
        return avisos
    return avisos + [CheckWarning(
        "Nó LOCAL sem credencial: " + ", ".join(faltando),
        hint=(
            "A loja continua operando e gravando eventos na outbox; eles ficam "
            "guardados até alguém rodar `manage.py sync_install_node` com o "
            "pacote gerado na nuvem."
        ),
        id="synchronization.W003",
    )]
