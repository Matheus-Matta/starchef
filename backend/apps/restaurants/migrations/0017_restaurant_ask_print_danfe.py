from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('restaurants', '0016_linhas_da_comanda'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurant',
            name='ask_print_danfe',
            field=models.BooleanField(default=False),
        ),
    ]
