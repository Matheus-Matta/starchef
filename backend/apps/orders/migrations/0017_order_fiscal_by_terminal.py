from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0016_indice_do_quadro_do_kds'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='fiscal_by_terminal',
            field=models.BooleanField(default=False, help_text='A NFC-e desta venda é emitida pelo terminal (StarChef Desktop): a nuvem não emite.'),
        ),
    ]
