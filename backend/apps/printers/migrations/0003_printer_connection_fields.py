from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("printers", "0002_scale_sector_alter_printer_sector"),
    ]

    operations = [
        migrations.AddField(
            model_name="printer",
            name="connection_type",
            field=models.CharField(
                choices=[
                    ("windows", "Windows / USB"),
                    ("network", "TCP/IP"),
                    ("serial", "Serial"),
                ],
                default="windows",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="printer",
            name="host",
            field=models.GenericIPAddressField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="printer",
            name="port",
            field=models.PositiveIntegerField(default=9100),
        ),
        migrations.AddField(
            model_name="printer",
            name="timeout_seconds",
            field=models.PositiveIntegerField(default=10),
        ),
    ]
