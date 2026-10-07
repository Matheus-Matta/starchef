"""O que a posição de estoque ganhou para virar relatório.

Filtros por fornecedor e categoria, o código e o fornecedor na linha, e CSV.
O insumo não tem categoria própria: a categoria é a dos produtos que o
consomem — vendidos direto da prateleira (`stock_ingredient`) ou pela ficha
técnica.
"""
import csv
from decimal import Decimal

from django.db.models import Q
from django.http import HttpResponse

CENTAVOS = Decimal("0.01")


def filtrar_insumos(insumos, params):
    fornecedor = params.get("supplier")
    if fornecedor:
        insumos = insumos.filter(supplier_id=fornecedor)
    categoria = params.get("category")
    if categoria:
        insumos = insumos.filter(
            Q(direct_products__category_id=categoria)
            | Q(recipe_items__recipe__product__category_id=categoria)
        ).distinct()
    return insumos.select_related("supplier").prefetch_related("direct_products")


def dados_extras(insumo):
    direto = next(iter(insumo.direct_products.all()), None)
    return {
        "code": (direto.internal_code if direto else "") or "",
        "supplier_id": str(insumo.supplier_id) if insumo.supplier_id else None,
        "supplier_name": insumo.supplier.name if insumo.supplier_id else "",
    }


def csv_da_posicao(linhas):
    resposta = HttpResponse(content_type="text/csv; charset=utf-8")
    resposta["Content-Disposition"] = 'attachment; filename="posicao_de_estoque.csv"'
    escritor = csv.writer(resposta)
    escritor.writerow(["Código", "Insumo", "Fornecedor", "Saldo", "Unidade", "Custo unitário", "Valor total"])
    for linha in linhas:
        escritor.writerow([
            linha["code"], linha["ingredient_name"], linha["supplier_name"],
            Decimal(linha["balance"]).quantize(Decimal("0.001")), linha["unit"],
            Decimal(linha["average_cost"]).quantize(CENTAVOS), linha["stock_value"],
        ])
    return resposta
