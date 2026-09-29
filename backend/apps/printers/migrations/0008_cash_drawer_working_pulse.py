from django.db import migrations, models


def configure_escpos_drawers(apps, schema_editor):
    printer = apps.get_model("printers", "Printer")
    printer.objects.filter(
        driver_type="escpos",
        cash_drawer_on_ms=100,
        cash_drawer_off_ms=400,
    ).update(
        cash_drawer_enabled=True,
        cash_drawer_on_ms=50,
        cash_drawer_off_ms=500,
    )


class Migration(migrations.Migration):
    dependencies = [("printers", "0007_printer_cash_drawer")]

    operations = [
        migrations.AlterField(
            model_name="printer",
            name="cash_drawer_on_ms",
            field=models.PositiveSmallIntegerField(
                default=50,
                help_text="Tempo com a bobina energizada. O padrao de 50 ms gera t1=25 no comando ESC/POS.",
            ),
        ),
        migrations.AlterField(
            model_name="printer",
            name="cash_drawer_off_ms",
            field=models.PositiveSmallIntegerField(
                default=500,
                help_text="Intervalo desligado depois do pulso. O padrao de 500 ms gera t2=250 no comando ESC/POS.",
            ),
        ),
        migrations.RunPython(configure_escpos_drawers, migrations.RunPython.noop),
    ]
