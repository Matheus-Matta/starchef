"""O insumo vira cadastro da conta, e os repetidos por restaurante viram um so.

"Farinha de trigo" cadastrada em tres unidades eram tres insumos diferentes,
com tres saldos e tres historicos. Quem localiza o estoque e o ARMAZEM, nao o
insumo — entao o certo e um insumo por conta, e o saldo de cada unidade sai da
soma dos armazens dela.

A unificacao precisa acontecer ANTES da nova unicidade (conta + nome), senao a
constraint nao entra. Ela e conservadora de proposito:

* mantem o registro mais antigo de cada nome (o que tem mais historico atras);
* repoe TODAS as referencias dos repetidos para ele — lotes, movimentos, itens
  de entrada e saida, itens de receita e o vinculo de produto;
* soma o estoque minimo? Nao: mantem o MAIOR informado, porque somar
  inventaria uma exigencia que ninguem definiu;
* apaga logicamente os repetidos, preservando o registro para auditoria.

Nada e removido de verdade, e nenhum saldo se perde: os lotes continuam
existindo, apenas apontando para o insumo que ficou.
"""
from django.db import migrations, models


def _normalized(name):
    return " ".join(str(name or "").split()).casefold()


def unify_ingredients_per_account(apps, schema_editor):
    Ingredient = apps.get_model("menu", "Ingredient")
    Product = apps.get_model("menu", "Product")
    RecipeItem = apps.get_model("menu", "RecipeItem")
    StockEntryItem = apps.get_model("stock", "StockEntryItem")
    StockExitItem = apps.get_model("stock", "StockExitItem")
    StockLot = apps.get_model("stock", "StockLot")
    StockMovement = apps.get_model("stock", "StockMovement")

    # `related_name` -> model, para repontar tudo que aponta para o insumo.
    referrers = (
        (StockEntryItem, "ingredient"),
        (StockExitItem, "ingredient"),
        (StockLot, "ingredient"),
        (StockMovement, "ingredient"),
        (RecipeItem, "ingredient"),
        (Product, "stock_ingredient"),
    )

    groups = {}
    for ingredient in Ingredient.objects.filter(deleted_at__isnull=True).order_by("created_at", "id"):
        groups.setdefault((ingredient.account_id, _normalized(ingredient.name)), []).append(ingredient)

    for (_account_id, _name), members in groups.items():
        keeper = members[0]
        duplicates = members[1:]

        # Mesmo sem repetidos, o vinculo de restaurante/filial sai: o insumo
        # passa a valer para a conta inteira.
        if keeper.restaurant_id is not None or keeper.branch_id is not None:
            keeper.restaurant_id = None
            keeper.branch_id = None
            keeper.save(update_fields=["restaurant", "branch", "updated_at"])
        if not duplicates:
            continue

        for model, field in referrers:
            model.objects.filter(**{f"{field}_id__in": [item.id for item in duplicates]}).update(
                **{f"{field}_id": keeper.id}
            )

        # O maior estoque minimo informado entre os repetidos continua valendo:
        # baixar a exigencia sem ninguem pedir esconderia uma ruptura.
        minimums = [item.minimum_stock for item in members if item.minimum_stock is not None]
        if minimums and keeper.minimum_stock != max(minimums):
            keeper.minimum_stock = max(minimums)
            keeper.save(update_fields=["minimum_stock", "updated_at"])

        from django.utils import timezone

        Ingredient.objects.filter(id__in=[item.id for item in duplicates]).update(
            deleted_at=timezone.now()
        )


def noop_reverse(apps, schema_editor):
    """A unificacao nao se desfaz.

    Reverter significaria adivinhar de qual dos insumos originais cada lote
    veio — e essa informacao deixa de existir no momento em que eles se
    juntam. A migracao para tras existe so para nao travar um `migrate` de
    volta no esquema; os dados ficam como estao.
    """


class Migration(migrations.Migration):
    dependencies = [
        ("menu", "0004_ingredient_supplier"),
        ("stock", "0004_supplier_stockentryitem_supplier_and_more"),
    ]

    operations = [
        migrations.RunPython(unify_ingredients_per_account, noop_reverse),
        migrations.RemoveConstraint(
            model_name="ingredient",
            name="unique_ingredient_by_branch",
        ),
        migrations.RemoveIndex(
            model_name="ingredient",
            name="menu_ingred_branch__b55764_idx",
        ),
        migrations.AddIndex(
            model_name="ingredient",
            index=models.Index(fields=["account", "is_active"], name="menu_ingred_account_f15790_idx"),
        ),
        migrations.AddConstraint(
            model_name="ingredient",
            constraint=models.UniqueConstraint(
                condition=models.Q(deleted_at__isnull=True),
                fields=("account", "name"),
                name="unique_ingredient_by_account",
            ),
        ),
    ]
