"""O id da chave de idempotência passa de inteiro sequencial a UUID derivado.

O id sequencial começava em 1 na loja e na nuvem: o registro 5 de um lado e o
5 do outro eram operações diferentes, e a sincronização não tinha como levar a
chave de um nó ao outro sem que uma apagasse a outra. Agora o id é
`uuid5(conta:chave)` — a mesma operação tem o mesmo id nos dois bancos.

Trocar o tipo da chave primária no lugar não funciona igual no SQLite e no
PostgreSQL, então a troca é por tabela nova: a antiga é renomeada, os
registros são copiados com o id calculado e ela é apagada. A tabela nova tem
nome próprio porque o PostgreSQL mantém os nomes dos índices na tabela
renomeada, e os da nova (derivados do nome) colidiriam com eles.
"""
import uuid

import django.db.models.deletion
from django.db import migrations, models

NAMESPACE = uuid.UUID("6f1d5c2e-8a4b-4c3e-9b7a-2d1e0f3c4b5a")


def copiar(apps, schema_editor):
    antigo = apps.get_model("core", "IdempotencyRecordLegado")
    novo = apps.get_model("core", "IdempotencyRecord")
    lote = []
    for registro in antigo.objects.all().iterator(chunk_size=1000):
        lote.append(novo(
            id=uuid.uuid5(NAMESPACE, f"{registro.account_id}:{registro.key}"),
            account_id=registro.account_id, key=registro.key, method=registro.method,
            path=registro.path, request_fingerprint=registro.request_fingerprint,
            status_code=registro.status_code, response_body=registro.response_body,
            created_at=registro.created_at,
        ))
        if len(lote) >= 1000:
            novo.objects.bulk_create(lote, ignore_conflicts=True)
            lote = []
    if lote:
        novo.objects.bulk_create(lote, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="idempotencyrecord", name="idempotency_unique_key_per_account",
        ),
        migrations.RemoveIndex(
            model_name="idempotencyrecord", name="core_idempo_created_c8a89f_idx",
        ),
        migrations.RenameModel(old_name="IdempotencyRecord", new_name="IdempotencyRecordLegado"),
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                ("id", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("key", models.CharField(max_length=200)),
                ("method", models.CharField(max_length=10)),
                ("path", models.CharField(max_length=500)),
                ("request_fingerprint", models.CharField(max_length=64)),
                ("status_code", models.PositiveSmallIntegerField()),
                ("response_body", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("account", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="idempotency_records", to="accounts.account",
                )),
            ],
            options={
                "db_table": "core_idempotency_record",
                "indexes": [models.Index(fields=["created_at"], name="core_idempotency_created_idx")],
                "constraints": [models.UniqueConstraint(
                    fields=("account", "key"), name="idempotency_unique_key_per_account",
                )],
            },
        ),
        migrations.RunPython(copiar, migrations.RunPython.noop),
        migrations.DeleteModel(name="IdempotencyRecordLegado"),
    ]
