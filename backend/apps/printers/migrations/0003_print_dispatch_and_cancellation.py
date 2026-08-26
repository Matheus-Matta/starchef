import uuid

import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0004_kitchen_dispatch_grace_period"),
        ("printers", "0002_unify_payment_receipts"),
    ]

    operations = [
        migrations.AddField(
            model_name="printjob",
            name="serial",
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
        migrations.AddField(
            model_name="printjob",
            name="available_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="printjob",
            name="original_job",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cancellation_jobs",
                to="printers.printjob",
            ),
        ),
        migrations.AddField(
            model_name="printjob",
            name="cancelled_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="cancellation_print_jobs",
                to="orders.orderitem",
            ),
        ),
        migrations.AddConstraint(
            model_name="printjob",
            constraint=models.UniqueConstraint(
                fields=("original_job", "cancelled_item"),
                condition=Q(original_job__isnull=False, cancelled_item__isnull=False),
                name="unique_cancel_job_per_original_item",
            ),
        ),
    ]
