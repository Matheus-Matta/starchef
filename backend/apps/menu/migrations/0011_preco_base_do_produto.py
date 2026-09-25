from django.db import migrations, models


class Migration(migrations.Migration):
    """As colunas de preco ganham o prefixo `base_`, e os nomes antigos viram
    propriedades dinamicas no model.

    E RenameField, e nao "cria nova + copia + apaga velha": o rename preserva o
    dado no lugar, sem janela em que o preco existe em duas colunas e alguem
    le a errada. A conversao que o pedido pedia e exatamente esta — o valor
    cadastrado passa a morar em `base_price`, e `sale_price` continua
    respondendo, agora por calculo.
    """

    dependencies = [("menu", "0010_alter_product_controls_stock_and_more")]

    operations = [
        migrations.RenameField(
            model_name="product",
            old_name="sale_price",
            new_name="base_price",
        ),
        migrations.RenameField(
            model_name="product",
            old_name="promotional_price",
            new_name="base_promotional_price",
        ),
        migrations.AlterField(
            model_name="product",
            name="base_price",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Preço cheio cadastrado. Por unidade, ou por kg quando pricing_unit=kg.",
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="product",
            name="base_promotional_price",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Promocional do próprio cadastro, sem data. Tabela de desconto desconta sobre ele.",
                max_digits=12,
                null=True,
            ),
        ),
    ]
