import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


def backfill_positions(apps, schema_editor):
    OrderItem = apps.get_model("orders", "OrderItem")
    Position = apps.get_model("kitchen", "KdsItemPosition")
    rows = OrderItem._base_manager.exclude(kds_column=None).values(
        "id", "account_id", "kds_column_id", "kds_column__station_id",
    )
    Position._base_manager.bulk_create([
        Position(
            account_id=row["account_id"], station_id=row["kds_column__station_id"],
            item_id=row["id"], column_id=row["kds_column_id"],
        )
        for row in rows
    ], ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("kitchen", "0001_initial"),
        ("orders", "0008_backfill_cancellation_details"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="kdsstation",
            name="rules",
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.CreateModel(
            name="KdsItemPosition",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("entered_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("account", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="%(class)s_set", to="accounts.account")),
                ("column", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="item_positions", to="kitchen.kdscolumn")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_created", to=settings.AUTH_USER_MODEL)),
                ("item", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="kds_positions", to="orders.orderitem")),
                ("station", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="item_positions", to="kitchen.kdsstation")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="%(class)s_updated", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [models.Index(fields=["station", "column"], name="kitchen_kds_station_426d76_idx")],
                "constraints": [models.UniqueConstraint(fields=("station", "item"), name="unique_kds_position_per_station_item")],
            },
        ),
        migrations.RunPython(backfill_positions, migrations.RunPython.noop),
    ]
