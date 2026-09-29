"""A gaveta deixa de ser uma caixa marcada e passa a seguir o driver.

`cash_drawer_enabled` nasceu como escolha do operador, mas a tela de cadastro
nunca ofereceu essa escolha: toda impressora criada por ali ficava com `False`
guardado. O PDV lia esse `False`, nao montava o pulso, e nada falhava em lugar
nenhum — a gaveta simplesmente nao abria, com o cabo RJ12 no lugar.

Esta migracao alinha as linhas que ja existem. E o que faz a gaveta abrir nos
terminais JA INSTALADOS, sem esperar a atualizacao de cada balcao: eles leem
`cash_drawer_enabled` do payload, e agora ele chega verdadeiro.
"""
from django.db import migrations, models


def cash_drawer_follows_the_driver(apps, schema_editor):
    printer = apps.get_model("printers", "Printer")
    for impressora in printer.objects.all().iterator():
        ligada = impressora.driver_type == "escpos"
        settings = impressora.settings if isinstance(impressora.settings, dict) else {}
        # O PDV le o cadastro nos dois niveis (direto e dentro de `settings`),
        # e guarda uma copia do dicionario inteiro junto do cupom na fila
        # local. Deixar os dois divergirem e deixar uma armadilha para depois.
        espelho_desatualizado = (
            "cash_drawer_enabled" in settings
            and settings["cash_drawer_enabled"] != ligada
        )
        if impressora.cash_drawer_enabled == ligada and not espelho_desatualizado:
            continue
        impressora.cash_drawer_enabled = ligada
        if "cash_drawer_enabled" in settings:
            settings["cash_drawer_enabled"] = ligada
            impressora.settings = settings
        impressora.save(update_fields=["cash_drawer_enabled", "settings"])


class Migration(migrations.Migration):
    dependencies = [("printers", "0008_cash_drawer_working_pulse")]

    operations = [
        migrations.AlterField(
            model_name="printer",
            name="cash_drawer_enabled",
            field=models.BooleanField(
                default=False,
                editable=False,
                help_text="Derivado do driver: toda impressora ESC/POS pode acionar a gaveta.",
            ),
        ),
        migrations.RunPython(
            cash_drawer_follows_the_driver,
            migrations.RunPython.noop,
        ),
    ]
