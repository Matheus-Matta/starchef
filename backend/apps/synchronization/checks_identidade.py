"""Avisos sobre a IDENTIDADE deste nó: quem ele diz ser, e quem está gravado.

Separado de `checks.py` porque é outro assunto: lá ficam os avisos sobre a
instalação poder conversar (chave, triggers, credenciais); aqui ficam os que
perguntam se este backend sabe QUEM ele é. Errar nisso não impede a conversa —
faz os dois lados numerarem na mesma faixa e entregarem o mesmo "pedido N".
"""
from django.conf import settings
from django.core.checks import Warning as CheckWarning

def _checar_papel_gravado(tipo):
    """A variável de ambiente concorda com a identidade gravada no banco?

    São duas fontes para o MESMO fato, e elas podem divergir sem nada
    reclamar: o `.env` diz um papel, o `SyncNode` desta instalação diz outro.
    Quem decide a faixa de numeração de pedido é a variável (a loja numera de
    1, a nuvem de 1.000.000) e quem decide o resto da sincronização é o
    registro.

    Divergir aí custa dinheiro de um jeito difícil de rastrear: uma loja que
    se acha nuvem numera na faixa da nuvem, os dois lados entregam o mesmo
    número, e quando a sincronização junta as bases aparecem dois "pedido
    1.000.002". O caixa do dia não fecha, e o erro que o operador vê é
    "já existe um registro com estes dados" — que não fala de nada disso.

    Aviso, e não erro, pelo princípio do módulo: sincronização mal configurada
    degrada a sincronização, não tira a loja do ar.
    """
    from apps.synchronization.services.nodes import self_node_or_none

    try:
        no = self_node_or_none()
    except Exception:  # noqa: BLE001 — banco ausente no `check` não é o assunto
        return []
    if no is None or not no.node_type or no.node_type == tipo:
        return []
    return [CheckWarning(
        f"SYNC_NODE_TYPE={tipo or '(vazio)'} mas o SyncNode desta instalação "
        f"está gravado como {no.node_type}.",
        hint=(
            "Os dois precisam dizer a mesma coisa. É a variável que escolhe a "
            "faixa de numeração de pedido (loja a partir de 1, nuvem a partir "
            "de 1.000.000): com ela errada, os dois nós entregam o mesmo "
            "número e a sincronização junta duas vendas com o mesmo 'pedido "
            "N'. Corrija o .env para bater com o registro — ou reinstale o nó."
        ),
        id="synchronization.W008",
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


def _checar_faixa_de_id():
    """A loja ainda numera usuário na mesma faixa que a nuvem?

    A migration `0009` empurra a sequência para fora dela. Este aviso existe
    para a instalação que já estava no ar quando a migration passou, ou que
    virou nó LOCAL depois. O porquê inteiro está em `services/user_ids.py`.
    """
    try:
        from django.db import connection

        from apps.synchronization.services import user_ids

        if not user_ids.dentro_da_faixa_da_nuvem(connection):
            return []
        atual = user_ids.valor_atual(connection)
    except Exception:  # noqa: BLE001 — banco ainda migrando, por exemplo
        return []

    return [CheckWarning(
        f"A sequência de `auth_user` está em {atual}, dentro da faixa que a "
        "nuvem usa.",
        hint=(
            "Um usuário criado nesta loja pode receber um id que a nuvem já "
            "deu a OUTRA pessoa, e a sincronização sobrescreveria uma com a "
            "outra sem erro visível — hash de senha inclusive. Rode "
            "`manage.py migrate synchronization`, que a 0009 reserva a faixa."
        ),
        id="synchronization.W007",
    )]
