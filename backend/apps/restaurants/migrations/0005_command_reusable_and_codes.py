from collections import defaultdict

from django.db import migrations, models


def backfill(apps, schema_editor):
    """Backfill de comandas e mesas para o novo esquema.

    - Command.number: sequencial por restaurante (estável por created_at).
    - Command.status: mapeia o antigo "open" (e qualquer valor legado) para "free".
    - Command.code / Table.code: default a partir do número quando vazio.
    """
    Command = apps.get_model("restaurants", "Command")
    Table = apps.get_model("restaurants", "Table")

    counters = defaultdict(int)
    for cmd in Command.objects.order_by("restaurant_id", "created_at", "id"):
        counters[cmd.restaurant_id] += 1
        cmd.number = counters[cmd.restaurant_id]
        if cmd.status not in ("free", "occupied"):
            cmd.status = "free"
        if not cmd.code:
            cmd.code = f"{cmd.number:04d}"
        cmd.save(update_fields=["number", "status", "code"])

    for tbl in Table.objects.all():
        if not tbl.code:
            tbl.code = str(tbl.number)
            tbl.save(update_fields=["code"])


class Migration(migrations.Migration):

    dependencies = [
        ("restaurants", "0004_restaurant_cash_action_password"),
    ]

    operations = [
        # ── Novos campos ─────────────────────────────────────────────────────
        migrations.AddField(
            model_name="command",
            name="number",
            field=models.PositiveIntegerField(default=0),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="command",
            name="current_order_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="table",
            name="code",
            field=models.CharField(blank=True, default="", max_length=40),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name="command",
            name="code",
            field=models.CharField(blank=True, max_length=40),
        ),
        migrations.AlterField(
            model_name="command",
            name="status",
            field=models.CharField(
                choices=[("free", "Free"), ("occupied", "Occupied")],
                db_index=True,
                default="free",
                max_length=24,
            ),
        ),
        migrations.AlterModelOptions(
            name="command",
            options={"ordering": ["number"]},
        ),
        # ── Backfill (antes de criar as constraints únicas) ──────────────────
        migrations.RunPython(backfill, migrations.RunPython.noop),
        # ── Constraints/índices ──────────────────────────────────────────────
        migrations.RemoveConstraint(
            model_name="command",
            name="unique_command_code_by_branch",
        ),
        migrations.AddConstraint(
            model_name="command",
            constraint=models.UniqueConstraint(
                fields=["restaurant", "number"], name="unique_command_number_by_restaurant"
            ),
        ),
        migrations.AddConstraint(
            model_name="command",
            constraint=models.UniqueConstraint(
                condition=models.Q(code__gt=""),
                fields=["restaurant", "code"],
                name="unique_command_code_by_restaurant",
            ),
        ),
        migrations.AddIndex(
            model_name="command",
            index=models.Index(fields=["restaurant", "status"], name="restaurants_restaur_5b6901_idx"),
        ),
        migrations.AddConstraint(
            model_name="table",
            constraint=models.UniqueConstraint(
                condition=models.Q(code__gt=""),
                fields=["branch", "code"],
                name="unique_table_code_by_branch",
            ),
        ),
    ]
