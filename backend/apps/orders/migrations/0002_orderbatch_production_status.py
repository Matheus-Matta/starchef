import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def migrate_order_production_status(apps, schema_editor):
    """Populate production_status from the old merged status field."""
    Order = apps.get_model("orders", "Order")
    mapping = {
        "sent_to_kitchen": "sent_to_kitchen",
        "preparing": "preparing",
        "partially_ready": "partially_ready",
        "ready": "ready",
        "delivered": "delivered",
    }
    for old_status, prod_status in mapping.items():
        Order.objects.filter(status=old_status).update(
            production_status=prod_status,
            status="open",
        )
    # paid orders that went through production
    Order.objects.filter(status="paid", production_status="idle").update(production_status="delivered")


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # 1. Add production_status to Order
        migrations.AddField(
            model_name="order",
            name="production_status",
            field=models.CharField(
                choices=[
                    ("idle", "Idle"),
                    ("sent_to_kitchen", "Sent to kitchen"),
                    ("preparing", "Preparing"),
                    ("partially_ready", "Partially ready"),
                    ("ready", "Ready"),
                    ("delivered", "Delivered"),
                ],
                db_index=True,
                default="idle",
                max_length=32,
            ),
        ),
        # 2. Update Order.status choices to remove production-related values
        migrations.AlterField(
            model_name="order",
            name="status",
            field=models.CharField(
                choices=[
                    ("open", "Open"),
                    ("awaiting_payment", "Awaiting payment"),
                    ("paid", "Paid"),
                    ("cancelled", "Cancelled"),
                    ("refunded", "Refunded"),
                ],
                db_index=True,
                default="open",
                max_length=32,
            ),
        ),
        # 3. Migrate existing data
        migrations.RunPython(migrate_order_production_status, migrations.RunPython.noop),
        # 4. Create OrderBatch model
        migrations.CreateModel(
            name="OrderBatch",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("batch_number", models.PositiveIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("done", "Done")],
                        default="sent",
                        max_length=20,
                    ),
                ),
                ("sent_at", models.DateTimeField()),
                ("printed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="accounts.account",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="restaurants.branch",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "order",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="batches",
                        to="orders.order",
                    ),
                ),
                (
                    "restaurant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)s_set",
                        to="restaurants.restaurant",
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="batches_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["batch_number"]},
        ),
        migrations.AddConstraint(
            model_name="orderbatch",
            constraint=models.UniqueConstraint(fields=("order", "batch_number"), name="unique_batch_number_per_order"),
        ),
        # 5. Add batch FK to OrderItem
        migrations.AddField(
            model_name="orderitem",
            name="batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="items",
                to="orders.orderbatch",
            ),
        ),
        # 6. Add void_reason to OrderItem (replaces cancel_reason)
        migrations.AddField(
            model_name="orderitem",
            name="void_reason",
            field=models.TextField(blank=True, default=""),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name="orderitem",
            name="cancel_reason",
        ),
        # 7. Update OrderItem.status choices to include comped
        migrations.AlterField(
            model_name="orderitem",
            name="status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
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
