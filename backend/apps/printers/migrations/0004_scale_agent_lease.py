from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("printers", "0003_printer_connection_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="scale",
            name="agent_instance_id",
            field=models.CharField(
                blank=True,
                help_text="Identificador do PDV Desktop que possui a leitura exclusiva da balanca.",
                max_length=120,
            ),
        ),
        migrations.AddField(
            model_name="scale",
            name="agent_lease_expires_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Validade da posse exclusiva da balanca pelo agente local.",
                null=True,
            ),
        ),
    ]
