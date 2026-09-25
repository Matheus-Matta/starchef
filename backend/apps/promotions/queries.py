"""Perguntas sobre promoção que o BANCO precisa responder, não o Python.

`pricing` resolve o preço de produtos que já estão na mão. Aqui é o contrário:
"quais produtos estão em promoção?", feita antes de buscar produto nenhum — o
cardápio digital tem um bloco de ofertas e o catálogo pode ter milhares de
itens. Trazer todos para filtrar em Python seria carregar o cardápio inteiro
para mostrar seis ofertas.
"""

from django.db.models import Q

from apps.promotions.models import Promotion
from apps.promotions.pricing import _regras_ativas

# Devolvido quando alguma regra alcança o cardápio inteiro. É um objeto próprio,
# e não `None`: `None` significaria "nenhuma promoção", e confundir os dois
# esconderia exatamente a promoção mais abrangente que existe.
TODOS = object()


def alvos_em_promocao(account_id, restaurant_id=None):
    """`TODOS`, ou `(ids_de_produto, ids_de_categoria, ids_de_setor)`."""
    regras = _regras_ativas(account_id, restaurant_id=restaurant_id)
    produtos, categorias, setores = set(), set(), set()
    for regra in regras:
        if regra.target_type == Promotion.TARGET_ALL:
            return TODOS
        if regra.target_type == Promotion.TARGET_PRODUCTS:
            produtos.update(regra.product_links.values_list("product_id", flat=True))
        elif regra.target_type == Promotion.TARGET_CATEGORIES:
            categorias.update(c.pk for c in regra.categories.all())
        elif regra.target_type == Promotion.TARGET_SECTORS:
            setores.update(s.pk for s in regra.sectors.all())
    return produtos, categorias, setores


def filtro_de_promocao(account_id, restaurant_id=None):
    """Um `Q` que casa todo produto com algum desconto ativo.

    Inclui o promocional MANUAL do cadastro: para quem olha a vitrine, "está em
    promoção" é uma coisa só — o cliente não distingue um preço promocional
    digitado no produto de um vindo de tabela de desconto, e nem deveria.
    """
    manual = Q(base_promotional_price__isnull=False)
    alvos = alvos_em_promocao(account_id, restaurant_id=restaurant_id)
    if alvos is TODOS:
        return Q()
    produtos, categorias, setores = alvos
    condicao = manual
    if produtos:
        condicao |= Q(pk__in=produtos)
    if categorias:
        condicao |= Q(category_id__in=categorias)
    if setores:
        condicao |= Q(sector_id__in=setores)
    return condicao
