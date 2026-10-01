"""Transformar um insumo em produto.

Caso real: a nota do fornecedor de bebidas foi vinculada a INSUMOS ("FANTA
LARANJA CX24") quando o certo era PRODUTO de revenda. Recadastrar à mão
perdia nome, unidade, custo e estoque mínimo; este gesto copia tudo.

O insumo NÃO é apagado: pode estar em ficha técnica ou ter saldo, e decidir
isso é do operador. Também não há transferência de saldo — o que já entrou no
estoque do insumo continua lá.
"""
import uuid
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.menu.models import UNIT_G, UNIT_KG, UNIT_L, UNIT_ML, Product

#: Unidade do insumo (minúscula, com `unit`) → unidade de estoque do produto.
_UNIDADE = {UNIT_KG: "KG", UNIT_G: "G", UNIT_L: "L", UNIT_ML: "ML"}


def transformar_em_produto(ingredient, *, user=None, restaurant=None):
    """Cria o produto a partir do insumo e devolve o produto criado."""
    restaurant = restaurant or ingredient.restaurant
    if restaurant is None:
        raise ValidationError(
            "Escolha o restaurante do produto: o insumo é da conta inteira."
        )
    custo = ingredient.average_cost or Decimal("0")
    with transaction.atomic():
        produto = Product.objects.create(
            account=ingredient.account,
            restaurant=restaurant,
            branch=ingredient.branch,
            name=ingredient.name,
            internal_code=f"PRD-{uuid.uuid4().hex[:6].upper()}",
            item_type=Product.ITEM_RESALE,
            stock_unit=_UNIDADE.get(ingredient.unit, "UN"),
            current_average_cost=custo,
            estimated_cost=custo.quantize(Decimal("0.01")),
            minimum_stock=ingredient.minimum_stock,
            controls_stock=True,
            is_active=ingredient.is_active,
            created_by=user,
            updated_by=user,
        )
        from apps.inbound_nfe.services.unlink import transferir_vinculos_para_produto

        transferir_vinculos_para_produto(ingredient, produto)
    return produto
