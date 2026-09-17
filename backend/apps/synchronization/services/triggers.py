"""Instala as triggers de rede de segurança no PostgreSQL (§11.2).

Só PostgreSQL. No SQLite do desenvolvimento a função vira um "não fiz nada" em
vez de um erro: a rede de segurança é uma garantia de produção, e exigi-la na
máquina de quem acabou de clonar o projeto só atrapalharia.

A trigger é deliberadamente burra. Ela grava `(tabela, id, operação)` e nada
mais — não monta payload, não calcula checksum, não decide destino. Tudo isso
continua em Python, com a mesma serialização que o resto usa. Uma trigger que
montasse o evento seria uma segunda implementação do `serialization.py`
escrita em PL/pgSQL, e as duas divergiriam no primeiro campo novo.

O laço é cortado por `app.sync_apply`: durante a aplicação de um evento
remoto, a sessão marca essa variável e a trigger não anota nada.
"""
import logging

from django.db import connection

logger = logging.getLogger(__name__)

FUNCAO = "starchef_sync_mark_dirty"
PREFIXO_TRIGGER = "starchef_sync_dirty_"

SQL_FUNCAO = f"""
CREATE OR REPLACE FUNCTION {FUNCAO}() RETURNS trigger AS $$
DECLARE
    id_alvo text;
    operacao text;
BEGIN
    -- Durante a aplicação de um evento remoto a sessão marca esta variável.
    -- Sem esta saída, aplicar um produto vindo da nuvem anotaria uma marca que
    -- viraria um evento de volta para a nuvem: o eco que o §13.2 proíbe.
    IF current_setting('app.sync_apply', true) = '1' THEN
        RETURN COALESCE(NEW, OLD);
    END IF;

    IF (TG_OP = 'DELETE') THEN
        id_alvo := OLD.id::text;
        operacao := 'DELETE';
    ELSE
        id_alvo := NEW.id::text;
        operacao := CASE WHEN TG_OP = 'INSERT' THEN 'CREATE' ELSE 'UPDATE' END;
    END IF;

    -- `error` entra explicitamente com string vazia. No Django ele é
    -- `TextField(blank=True)`, que NÃO é `null=True`: a coluna é NOT NULL e o
    -- default '' só existe no Python. Um INSERT que a omita recebe NULL e
    -- viola a constraint — e como isso acontece DENTRO da trigger, o efeito
    -- não é "a marca não foi gravada": é a gravação do PRÓPRIO dado de negócio
    -- falhando. Toda venda, todo pedido, em toda tabela sincronizada.
    INSERT INTO synchronization_syncdirty
        (id, table_name, row_id, operation, changed_at, error)
    VALUES
        (gen_random_uuid(), TG_TABLE_NAME, id_alvo, operacao, now(), '');

    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;
"""


def is_postgres():
    return connection.vendor == "postgresql"


def tabelas_sincronizadas():
    """As tabelas dos models do catálogo, com `id` do tipo UUID.

    Model sem `id` UUID fica de fora: a trigger grava `NEW.id::text` e uma
    chave composta ou sequencial não teria identidade global — que é a
    premissa de tudo (§6).
    """
    from apps.synchronization.services.registry import registry

    tabelas = []
    for entrada in registry.ordered():
        model = entrada.model
        pk = model._meta.pk
        if pk.name != "id" or pk.get_internal_type() not in ("UUIDField",):
            continue
        tabelas.append((model._meta.db_table, entrada.entity_type))
    return tabelas


def install(*, log=logger.info):
    """(Re)cria função e triggers. Idempotente: pode rodar em todo deploy."""
    if not is_postgres():
        log("sync: triggers só existem no PostgreSQL; nada a fazer neste banco.")
        return 0

    instaladas = 0
    with connection.cursor() as cursor:
        cursor.execute(SQL_FUNCAO)
        for tabela, entity_type in tabelas_sincronizadas():
            nome = f"{PREFIXO_TRIGGER}{tabela}"[:63]
            cursor.execute(f'DROP TRIGGER IF EXISTS "{nome}" ON "{tabela}"')
            cursor.execute(
                f'CREATE TRIGGER "{nome}" AFTER INSERT OR UPDATE OR DELETE ON "{tabela}" '
                f"FOR EACH ROW EXECUTE FUNCTION {FUNCAO}()"
            )
            instaladas += 1
            log(f"  trigger em {tabela} ({entity_type})")
    log(f"sync: {instaladas} trigger(s) instalada(s).")
    return instaladas


def uninstall(*, log=logger.info):
    if not is_postgres():
        return 0
    removidas = 0
    with connection.cursor() as cursor:
        for tabela, _ in tabelas_sincronizadas():
            nome = f"{PREFIXO_TRIGGER}{tabela}"[:63]
            cursor.execute(f'DROP TRIGGER IF EXISTS "{nome}" ON "{tabela}"')
            removidas += 1
        cursor.execute(f"DROP FUNCTION IF EXISTS {FUNCAO}() CASCADE")
    log(f"sync: {removidas} trigger(s) removida(s).")
    return removidas


def installed():
    """Nomes das triggers existentes. Vazio fora do PostgreSQL."""
    if not is_postgres():
        return set()
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT tgname FROM pg_trigger WHERE tgname LIKE %s AND NOT tgisinternal",
            [f"{PREFIXO_TRIGGER}%"],
        )
        return {linha[0] for linha in cursor.fetchall()}


def faltando():
    """Tabelas sincronizadas SEM trigger. É o que o `check` reclama."""
    if not is_postgres():
        return []
    existentes = installed()
    return [
        tabela for tabela, _ in tabelas_sincronizadas()
        if f"{PREFIXO_TRIGGER}{tabela}"[:63] not in existentes
    ]


def mark_apply_session(cursor=None):
    """Liga `app.sync_apply` NA TRANSAÇÃO atual (`SET LOCAL`).

    `SET LOCAL` e não `SET`: a marca tem de morrer com a transação. Um `SET`
    normal ficaria na conexão, e como o pool reaproveita conexões entre
    requisições, a próxima venda na mesma conexão nasceria sem evento.
    """
    if not is_postgres():
        return False
    if cursor is None:
        with connection.cursor() as novo:
            novo.execute("SET LOCAL app.sync_apply = '1'")
    else:
        cursor.execute("SET LOCAL app.sync_apply = '1'")
    return True
