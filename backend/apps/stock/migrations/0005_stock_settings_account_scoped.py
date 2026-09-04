"""A configuracao de estoque passa a ser da conta, e as por filial viram uma so.

FIFO/FEFO, obrigatoriedade de validade, bloqueio de vencido e de saldo negativo
sao politica da empresa: o mesmo insumo vence do mesmo jeito em qualquer
armazem. Uma configuracao por filial obrigava a repetir a decisao em cada
unidade — e deixava a rede operando com regras diferentes sem ninguem perceber.

A unificacao precisa acontecer ANTES da nova unicidade (uma por conta), senao a
constraint nao entra. Mantem a configuracao mais antiga de cada conta, por ser a
que a operacao vem seguindo ha mais tempo, e apaga logicamente as demais —
preservando o registro para auditoria.

O `default_location` da que ficou continua apontando para o armazem que estava
escolhido. Ele nao localiza estoque nenhum: serve so para pre-selecionar o
armazem numa saida, e o operador troca quando precisa.
"""
import django.db.models.deletion
from django.db import migrations, models


def unify_settings_per_account(apps, schema_editor):
    StockSettings = apps.get_model("stock", "StockSettings")
    from django.utils import timezone

    seen = set()
    for config in StockSettings.objects.filter(deleted_at__isnull=True).order_by("created_at", "id"):
        if config.account_id in seen:
            # Ja existe a configuracao desta conta: esta vira historico.
            StockSettings.objects.filter(pk=config.pk).update(deleted_at=timezone.now())
            continue
        seen.add(config.account_id)
        if config.restaurant_id is not None or config.branch_id is not None:
            config.restaurant_id = None
            config.branch_id = None
            config.save(update_fields=["restaurant", "branch", "updated_at"])


def noop_reverse(apps, schema_editor):
    """A unificacao nao se desfaz.

    Reverter exigiria saber qual configuracao era de qual filial — e isso deixa
    de existir quando elas viram uma. A migracao para tras existe so para nao
    travar um `migrate` de volta no esquema.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("stock", "0004_supplier_stockentryitem_supplier_and_more"),
    ]

    operations = [
        migrations.RunPython(unify_settings_per_account, noop_reverse),
        migrations.RemoveConstraint(
            model_name="stocksettings",
            name="unique_stock_settings_by_branch",
        ),
        migrations.AlterField(
            model_name="stocksettings",
            name="restaurant",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(class)s_set",
                to="restaurants.restaurant",
            ),
        ),
        migrations.AddConstraint(
            model_name="stocksettings",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=("account",),
                name="unique_stock_settings_by_account",
            ),
        ),
    ]
