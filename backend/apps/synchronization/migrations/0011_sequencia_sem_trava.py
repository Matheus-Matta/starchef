"""A sequence do número do evento (ver `services/sequencia_pg.py`).

Nasce acima de tudo que já existe: do maior evento de saída e do contador de
cada nó. Fora do PostgreSQL não faz nada — lá o contador da linha continua.
"""
from django.db import migrations

NOME = "sync_event_sequence"


def criar(apps, schema_editor):
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f"CREATE SEQUENCE IF NOT EXISTS {NOME} AS bigint START 1")
        cursor.execute(
            "SELECT greatest("
            " (SELECT coalesce(max(sequence), 0) FROM synchronization_syncevent"
            "  WHERE direction = 'OUTBOUND'),"
            " (SELECT coalesce(max(sequence_counter), 0) FROM synchronization_syncnode))"
        )
        maior = int(cursor.fetchone()[0] or 0)
        if maior:
            cursor.execute("SELECT setval(%s, %s)", [NOME, maior])


def apagar(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        with schema_editor.connection.cursor() as cursor:
            cursor.execute(f"DROP SEQUENCE IF EXISTS {NOME}")


class Migration(migrations.Migration):
    dependencies = [("synchronization", "0010_no_registra_quando_perdeu_contato")]
    operations = [migrations.RunPython(criar, apagar)]
