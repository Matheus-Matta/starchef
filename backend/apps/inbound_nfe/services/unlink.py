"""Desfazer o vínculo de um item da NF-e com o cadastro interno.

O operador vincula o item errado (outro produto, ou produto no lugar de
patrimônio) e precisa voltar atrás. Limpar o item não basta: o `map` também
ENSINA o sistema (`SupplierItemMapping` e a conversão de unidade do produto), e
a próxima nota do mesmo fornecedor seria vinculada errado de novo, sozinha.

Depois que a nota entrou no estoque não há o que desfazer aqui: o item já
gerou movimento, e trocar o vínculo deixaria o estoque de um produto e a nota
apontando para outro.
"""
from django.db import models, transaction

from apps.inbound_nfe.models import InboundNFe, InboundNFeItem, SupplierItemMapping


class VinculoTravado(Exception):
    """O estado da nota não permite mexer no vínculo (409, não 400)."""


def assert_item_editable(invoice, item):
    if invoice.status == InboundNFe.STATUS_RECEIVED or item.stock_movement_id:
        raise VinculoTravado(
            "Esta nota já entrou no estoque: o vínculo não pode mais ser alterado."
        )
    if invoice.status == InboundNFe.STATUS_CANCELLED:
        raise VinculoTravado("Nota cancelada: o vínculo não pode ser alterado.")


def _esquecer_aprendizado(invoice, item, product, ingredient):
    """Apaga só o aprendizado que aponta para o vínculo errado.

    Apagar DE VERDADE, e não a exclusão lógica do `TenantModel`: o
    `save_mapping` procura em `all_objects`, acharia a linha apagada e a
    regravaria com `deleted_at` preenchido — o vínculo refeito ficaria
    invisível para o casamento automático para sempre.
    """
    cnpj = (invoice.supplier_cnpj or "").strip()
    if not cnpj:
        return
    code = (item.supplier_code or "").strip()
    ean = (item.ean or "").strip()
    chave = models.Q()
    if code:
        chave |= models.Q(supplier_code=code)
    if ean:
        chave |= models.Q(supplier_ean=ean)
    if chave:
        aprendidos = SupplierItemMapping.all_objects.filter(
            chave, account=invoice.account, supplier_cnpj=cnpj,
            product=product, ingredient=ingredient,
        )
        for mapping in aprendidos:
            models.Model.delete(mapping)
    if product is not None:
        from apps.menu.models import ProductUnitConversion

        ProductUnitConversion.all_objects.filter(
            account=invoice.account, product=product,
            supplier_cnpj=cnpj, supplier_product_code=code,
        ).delete()


def unlink_item(item_id, *, esquecer=True):
    """Tira o vínculo do item e devolve a nota para "mapeamento pendente"."""
    with transaction.atomic():
        item = InboundNFeItem.all_objects.select_related("invoice").get(pk=item_id)
        # Trava a NOTA e relê o item depois da trava: o recebimento trava a
        # mesma nota, então um "desvincular" e um "receber" simultâneos não
        # podem os dois passar pela conferência acima.
        invoice = InboundNFe.all_objects.select_for_update().get(pk=item.invoice_id)
        item = InboundNFeItem.all_objects.select_for_update().get(pk=item_id)
        assert_item_editable(invoice, item)

        product, ingredient = item.product, item.ingredient
        if esquecer and (product is not None or ingredient is not None):
            _esquecer_aprendizado(invoice, item, product, ingredient)

        item.product = None
        item.ingredient = None
        item.conversion_factor = 1
        item.save(update_fields=["product", "ingredient", "conversion_factor"])

        if not item.is_ignored and invoice.status != InboundNFe.STATUS_IGNORED:
            invoice.status = InboundNFe.STATUS_PENDING_MAPPING
            invoice.save(update_fields=["status"])
    return item


def liberar_vinculos_de_apagado(*, product=None, ingredient=None):
    """Solta o que ainda aponta para um produto/insumo que foi excluído.

    Excluir é só marcar `deleted_at`: a chave estrangeira continua lá. Sem
    isto, o item seguia "Ingrediente: X" na tela, a nota contava como
    vinculada e o recebimento dava entrada num cadastro apagado — e o
    aprendizado do fornecedor religava a próxima nota ao mesmo apagado.

    Nota já recebida fica como está: o estoque já entrou, e o vínculo é o
    registro de onde ele foi parar.
    """
    alvo = {"product": product} if product is not None else {"ingredient": ingredient}
    if not any(alvo.values()):
        return 0
    with transaction.atomic():
        itens = InboundNFeItem.all_objects.filter(
            stock_movement__isnull=True, **alvo
        ).exclude(invoice__status=InboundNFe.STATUS_RECEIVED)
        notas = set(itens.values_list("invoice_id", flat=True))
        soltos = itens.update(product=None, ingredient=None, conversion_factor=1)
        InboundNFe.all_objects.filter(
            pk__in=notas,
            status__in=[InboundNFe.STATUS_PENDING_RECEIPT, InboundNFe.STATUS_XML_AVAILABLE],
        ).update(status=InboundNFe.STATUS_PENDING_MAPPING)
        for mapping in SupplierItemMapping.all_objects.filter(**alvo):
            models.Model.delete(mapping)
    return soltos


def transferir_vinculos_para_produto(ingredient, product):
    """Passa do insumo para o produto o que ainda não entrou no estoque.

    Itens de notas não recebidas e o aprendizado do fornecedor. Nota recebida
    fica: o saldo entrou no insumo, e é ali que o vínculo diz que ele está.
    """
    pendentes = InboundNFeItem.all_objects.filter(
        ingredient=ingredient, stock_movement__isnull=True
    ).exclude(invoice__status=InboundNFe.STATUS_RECEIVED)
    movidos = pendentes.update(ingredient=None, product=product)
    SupplierItemMapping.all_objects.filter(ingredient=ingredient).update(
        ingredient=None, product=product
    )
    return movidos
