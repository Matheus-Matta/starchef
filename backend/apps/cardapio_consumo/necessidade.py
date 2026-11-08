"""O que um cardápio tira do estoque, em insumos, e quanto há no local.

O estoque é controlado por INSUMO. Um produto do cardápio é aberto como a
venda abre (`stock/services/order_stock.py`): pela ficha técnica, rateada pelo
rendimento; sem ficha, pelo insumo direto do cadastro. Aqui a ficha vale mesmo
com a "baixa automática na venda" desligada — ela desliga a VENDA, e quem
pôs o produto no cardápio pediu a baixa dele.
"""
from dataclasses import dataclass, field
from decimal import Decimal

from apps.menu.units import IncompatibleUnitError, convert
from apps.stock.lots import QUANTITY_PLACES, pickable_lots, settings_for


@dataclass
class Necessidade:
    #: id do insumo → [insumo, quantidade na unidade do insumo]
    por_insumo: dict = field(default_factory=dict)
    #: o que não deu para baixar e por quê, em texto para a tela e o sino
    avisos: list = field(default_factory=list)

    def somar(self, ingredient, quantidade, unidade, origem):
        try:
            convertida = convert(Decimal(str(quantidade)), unidade or ingredient.unit, ingredient.unit)
        except IncompatibleUnitError:
            self.avisos.append(f"{origem}: {unidade} não converte para {ingredient.unit} ({ingredient.name}).")
            return
        atual = self.por_insumo.setdefault(str(ingredient.pk), [ingredient, Decimal("0")])
        atual[1] += Decimal(str(convertida))

    def linhas(self):
        """[(insumo, quantidade)] arredondado, na ordem do nome."""
        linhas = [(ing, qtd.quantize(QUANTITY_PLACES)) for ing, qtd in self.por_insumo.values()]
        return sorted((linha for linha in linhas if linha[1] > 0), key=lambda linha: linha[0].name)


def necessidade_do_cardapio(cardapio, necessidade=None):
    necessidade = necessidade or Necessidade()
    itens = cardapio.itens.filter(deleted_at__isnull=True).select_related(
        "ingredient", "product__stock_ingredient")
    for item in itens:
        if item.ingredient_id:
            necessidade.somar(item.ingredient, item.quantidade, item.unidade, item.ingredient.name)
        else:
            _abrir_produto(item.product, Decimal(str(item.quantidade)), necessidade)
    return necessidade


def _abrir_produto(product, quantidade, necessidade):
    recipe = getattr(product, "recipe", None)
    if recipe is not None and recipe.is_active and recipe.deleted_at is None:
        rendimento = Decimal(str(recipe.yield_quantity or 1)) or Decimal("1")
        for item in recipe.items.filter(deleted_at__isnull=True).select_related("ingredient"):
            por_rendimento = Decimal(str(item.quantity)) / rendimento
            necessidade.somar(item.ingredient, por_rendimento * quantidade, item.unit, product.name)
        return
    por_unidade = Decimal(str(product.stock_consumption_quantity or 0))
    if product.stock_ingredient_id and por_unidade > 0:
        necessidade.somar(product.stock_ingredient, por_unidade * quantidade,
                          product.stock_consumption_unit, product.name)
        return
    necessidade.avisos.append(
        f"{product.name}: sem ficha técnica nem insumo de estoque no cadastro — ficou de fora da baixa."
    )


def saldo_no_local(ingredient, local, config=None):
    """O que dá para tirar agora: os lotes que a separação escolheria."""
    config = config or settings_for(local.account)
    lotes = pickable_lots(ingredient=ingredient, location=local, strategy=config.picking_strategy,
                          block_expired=config.block_expired_stock)
    return sum((Decimal(str(lote.quantity)) for lote in lotes), Decimal("0")).quantize(QUANTITY_PLACES)
