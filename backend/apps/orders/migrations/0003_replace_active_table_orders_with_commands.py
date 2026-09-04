from django.db import migrations, models
from django.db.models import Max


ACTIVE_ORDER_STATUSES = ("open", "awaiting_payment")


def migrate_active_table_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    Command = apps.get_model("restaurants", "Command")
    Table = apps.get_model("restaurants", "Table")

    active_orders = Order.objects.filter(
        order_type="table",
        status__in=ACTIVE_ORDER_STATUSES,
    ).order_by("restaurant_id", "opened_at", "id")
    next_numbers = {}

    for order in active_orders.iterator():
        command = None
        if order.command_id:
            command = Command.objects.filter(pk=order.command_id).first()
        if command is None:
            command = (
                Command.objects.filter(
                    account_id=order.account_id,
                    restaurant_id=order.restaurant_id,
                    current_order_id__isnull=True,
                    status="free",
                    is_active=True,
                    deleted_at__isnull=True,
                )
                .order_by("number")
                .first()
            )
        if command is None:
            key = order.restaurant_id
            if key not in next_numbers:
                maximum = Command.objects.filter(restaurant_id=key).aggregate(value=Max("number"))["value"] or 0
                next_numbers[key] = maximum + 1
            number = next_numbers[key]
            next_numbers[key] += 1
            command = Command.objects.create(
                account_id=order.account_id,
                restaurant_id=order.restaurant_id,
                branch_id=order.branch_id,
                number=number,
                code=f"{number:04d}",
                created_by_id=order.created_by_id,
                updated_by_id=order.updated_by_id,
            )

        Order.objects.filter(pk=order.pk).update(
            order_type="command",
            command_id=command.pk,
        )
        Command.objects.filter(pk=command.pk).update(
            status="occupied",
            current_order_id=order.pk,
            current_table_id=order.table_id,
            updated_by_id=order.updated_by_id,
        )

    # A ocupação da mesa passa a ser determinada só por comandas vinculadas.
    for table in Table.objects.all().iterator():
        has_commands = Command.objects.filter(
            current_table_id=table.pk,
            deleted_at__isnull=True,
        ).exists()
        fields = {"current_order_id": None}
        if has_commands:
            fields["status"] = "occupied"
        elif table.status == "occupied":
            fields["status"] = "free"
        Table.objects.filter(pk=table.pk).update(**fields)


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0002_order_service_fee_enabled_and_ordering"),
        ("restaurants", "0002_command_current_table_commandmovementlog"),
    ]

    operations = [
        migrations.RunPython(migrate_active_table_orders, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="order",
            name="order_type",
            field=models.CharField(
                choices=[
                    ("command", "Command"),
                    ("counter", "Counter"),
                    ("delivery", "Delivery"),
                    ("takeaway", "Takeaway"),
                    ("internal", "Internal"),
                ],
                max_length=24,
            ),
        ),
    ]
