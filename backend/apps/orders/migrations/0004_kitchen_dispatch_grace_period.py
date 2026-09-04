import uuid

from django.db import migrations, models


def populate_order_batch_serials(apps, schema_editor):
    order_batch = apps.get_model("orders", "OrderBatch")
    pending = []
    for batch in order_batch.objects.filter(serial__isnull=True).iterator(chunk_size=1000):
        batch.serial = uuid.uuid4()
        pending.append(batch)
        if len(pending) == 1000:
            order_batch.objects.bulk_update(pending, ["serial"])
            pending.clear()
    if pending:
        order_batch.objects.bulk_update(pending, ["serial"])


class Migration(migrations.Migration):
    dependencies = [("orders", "0003_replace_active_table_orders_with_commands")]

    operations = [
        migrations.AddField(
            model_name="orderbatch",
            name="serial",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.RunPython(
            populate_order_batch_serials,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name="orderbatch",
            name="serial",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="orderbatch",
            name="dispatch_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name="orderbatch",
            name="status",
            field=models.CharField(
                choices=[
                    ("scheduled", "Scheduled"),
                    ("sent", "Sent"),
                    ("done", "Done"),
                    ("cancelled", "Cancelled"),
                ],
                default="scheduled",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="orderitem",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("queued", "Queued during grace period"),
                    ("sent", "Sent"),
                    ("preparing", "Preparing"),
                    ("ready", "Ready"),
                    ("delivered", "Delivered"),
                    ("cancelled", "Cancelled"),
                    ("comped", "Comped"),
                ],
                db_index=True,
                default="pending",
                max_length=24,
            ),
        ),
    ]
