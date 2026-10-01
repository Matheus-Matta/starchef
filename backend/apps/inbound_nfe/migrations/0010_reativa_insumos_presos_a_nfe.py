"""Desfaz as exclusões que ficaram presas a NF-e de entrada.

Antes desta versão, excluir um insumo ou produto só marcava `deleted_at`: o
item da nota continuava "Ingrediente: X", a nota contava como vinculada e o
aprendizado do fornecedor religava a próxima nota ao mesmo cadastro apagado.
A exclusão agora solta isso sozinha (ver `signals.py`), mas só para o que for
excluído DAQUI EM DIANTE.

INSUMO: é REATIVADO, para o operador excluir de novo pelo caminho certo. Só os
que ainda estão presos a uma nota ou a um aprendizado — reativar todo insumo
apagado traria de volta o que foi excluído de propósito em outras contas. Se
já existir um insumo ATIVO com o mesmo nome (alguém recriou), o antigo fica
apagado: reativá-lo quebraria o nome único da conta e o deploy.

PRODUTO: os itens de notas ainda não recebidas são soltos, como a exclusão
nova faria. Nota já recebida não é tocada — o estoque já entrou.
"""
from django.db import migrations
from django.db.models import Q


def desfazer(apps, schema_editor):
    Ingredient = apps.get_model("menu", "Ingredient")
    InboundNFe = apps.get_model("inbound_nfe", "InboundNFe")
    InboundNFeItem = apps.get_model("inbound_nfe", "InboundNFeItem")
    SupplierItemMapping = apps.get_model("inbound_nfe", "SupplierItemMapping")

    presos = set(
        InboundNFeItem.objects.filter(ingredient__deleted_at__isnull=False)
        .values_list("ingredient_id", flat=True)
    ) | set(
        SupplierItemMapping.objects.filter(ingredient__deleted_at__isnull=False)
        .values_list("ingredient_id", flat=True)
    )
    for insumo in Ingredient.objects.filter(pk__in=presos):
        nome_em_uso = Ingredient.objects.filter(
            account_id=insumo.account_id, name=insumo.name, deleted_at__isnull=True
        ).exists()
        if not nome_em_uso:
            Ingredient.objects.filter(pk=insumo.pk).update(deleted_at=None)

    produto_apagado = Q(product__deleted_at__isnull=False)
    itens = InboundNFeItem.objects.filter(
        produto_apagado, stock_movement__isnull=True
    ).exclude(invoice__status="received")
    notas = set(itens.values_list("invoice_id", flat=True))
    itens.update(product=None, ingredient=None, conversion_factor=1)
    InboundNFe.objects.filter(
        pk__in=notas, status__in=["pending_receipt", "xml_available"]
    ).update(status="pending_mapping")
    SupplierItemMapping.objects.filter(produto_apagado).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("inbound_nfe", "0009_inboundnfe_ignored_at_inboundnfe_ignored_by_and_more"),
        ("menu", "0011_preco_base_do_produto"),
    ]

    operations = [migrations.RunPython(desfazer, migrations.RunPython.noop)]
