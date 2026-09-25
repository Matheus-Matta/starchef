"""Quem decide o preço de um produto agora.

É AQUI, e em nenhum outro lugar. O preço cadastrado (`base_price`) nunca muda;
o que muda é qual promoção o alcança neste instante. Espalhar essa decisão pelo
serializer, pelo pedido e pelo PDV garantiria três respostas diferentes para a
mesma pergunta — e o cliente veria uma na vitrine e outra no cupom.

A ORDEM DA DISPUTA, quando mais de uma regra alcança o mesmo produto:
  1. a tabela MAIS ANTIGA ganha (foi o que o restaurante prometeu primeiro);
  2. dentro da tabela, a regra mais ao TOPO ganha (`position`).
A primeira regra que alcança o produto vence e a busca para. Não existe "soma
de descontos": dois descontos empilhados são como o restaurante perde dinheiro
sem ninguém ter decidido isso.
"""

from dataclasses import dataclass
from decimal import Decimal

from apps.promotions.models import Promotion


@dataclass(frozen=True)
class Oferta:
    """O que uma promoção faz com um produto: o "por", o "de" e quem mandou."""

    price: Decimal
    compare_at: Decimal
    promotion_id: str
    promotion_name: str
    table_id: str
    table_name: str

    @property
    def discount_amount(self):
        return self.compare_at - self.price

    @property
    def discount_percent(self):
        if not self.compare_at:
            return Decimal("0.00")
        return ((self.compare_at - self.price) / self.compare_at * 100).quantize(Decimal("0.01"))


def _regras_ativas(account_id, restaurant_id=None):
    """As regras que podem valer, já na ordem da disputa.

    `all_objects` com `account_id` explícito de propósito: o manager padrão é
    escopado pela conta do REQUEST, e este código também roda fora de request
    (sincronização, tarefa, comando). Lá, `objects` devolve vazio em silêncio —
    e vazio aqui significa "nenhuma promoção", ou seja, cobrar o preço cheio de
    quem tinha direito ao desconto.
    """
    consulta = (
        Promotion.all_objects.filter(
            account_id=account_id,
            deleted_at__isnull=True,
            is_enabled=True,
            table__deleted_at__isnull=True,
            table__is_enabled=True,
        )
        .select_related("table")
        .prefetch_related("categories", "sectors")
    )
    if restaurant_id:
        # Tabela sem restaurante vale para a conta inteira; com restaurante,
        # só naquela loja. Sem isto, a promoção da filial do shopping
        # apareceria no caixa da loja de rua.
        from django.db.models import Q

        consulta = consulta.filter(Q(table__restaurant_id=None) | Q(table__restaurant_id=restaurant_id))
    regras = [regra for regra in consulta if regra.is_active]
    regras.sort(key=lambda r: (r.table.created_at, r.position, r.created_at))
    return regras


def _links_por_produto(regras, product_ids):
    """Os vínculos regra↔produto das regras que apontam produto direto.

    Uma consulta só, restrita aos produtos em questão: carregar todos os
    vínculos de uma tabela com o cardápio inteiro dentro faria a listagem de
    trinta produtos puxar milhares de linhas para usar trinta.
    """
    from apps.promotions.models import PromotionProduct

    alvo = [r.pk for r in regras if r.target_type == Promotion.TARGET_PRODUCTS]
    if not alvo or not product_ids:
        return {}
    vinculos = PromotionProduct.all_objects.filter(
        promotion_id__in=alvo,
        product_id__in=product_ids,
        deleted_at__isnull=True,
    )
    return {(v.promotion_id, v.product_id): v for v in vinculos}


def _alcanca(regra, product, link):
    if regra.target_type == Promotion.TARGET_ALL:
        return True
    if regra.target_type == Promotion.TARGET_PRODUCTS:
        return link is not None
    if regra.target_type == Promotion.TARGET_CATEGORIES:
        return bool(product.category_id) and any(c.pk == product.category_id for c in regra.categories.all())
    if regra.target_type == Promotion.TARGET_SECTORS:
        return bool(product.sector_id) and any(s.pk == product.sector_id for s in regra.sectors.all())
    return False


def preco_de_prateleira(product):
    """O preço do produto SEM nenhuma tabela de desconto: o da prateleira.

    É o promocional manual do cadastro quando existe, senão o preço cheio. As
    regras de categoria e setor descontam SOBRE ele, e é isso que garante que
    uma promoção jamais aumente um preço: "10% na categoria" aplicado a um
    produto que já estava com promocional manual de 15 dá 13,50 — e não 18,
    que é o que daria se o desconto incidisse sobre o preço cheio de 20.
    """
    manual = product.base_promotional_price
    if manual is not None and Decimal(manual) > 0:
        return Decimal(manual)
    return Decimal(product.base_price or 0)


def _oferta(regra, product, link):
    """Traduz regra + produto em preço. O "de" é o que será exibido riscado.

    Quando a regra aponta o produto direto, ela pode ditar os DOIS números
    (`compare_at_price` e `promotional_price`) — é assim que encarte funciona:
    "de 30 por 15" num produto cadastrado a 20. Nos outros alvos o "de" é o
    preço de prateleira, porque não há onde digitar outro.
    """
    prateleira = preco_de_prateleira(product)
    de_digitado = getattr(link, "compare_at_price", None)
    compare_at = Decimal(de_digitado) if de_digitado is not None else prateleira
    preco = regra.preco_para(prateleira, override=link)
    if preco >= compare_at and de_digitado is None:
        # Promoção que não baixa nada não é promoção: deixá-la "vencer"
        # esconderia a regra seguinte, que talvez descontasse de verdade.
        return None
    return Oferta(
        price=preco,
        compare_at=compare_at,
        promotion_id=str(regra.pk),
        promotion_name=regra.name,
        table_id=str(regra.table_id),
        table_name=regra.table.name,
    )


def ofertas_para(products, restaurant_id=None):
    """A oferta vencedora de cada produto da lista. Poucas consultas, fixas.

    Usado pelas LISTAGENS. Resolver produto a produto custaria uma consulta por
    linha da grade — e o PDV carrega o cardápio inteiro na abertura do caixa.
    """
    products = [p for p in products if p is not None]
    if not products:
        return {}
    account_id = products[0].account_id
    regras = _regras_ativas(account_id, restaurant_id=restaurant_id)
    if not regras:
        return {}
    links = _links_por_produto(regras, [p.pk for p in products])
    resultado = {}
    for product in products:
        for regra in regras:
            link = links.get((regra.pk, product.pk))
            if not _alcanca(regra, product, link):
                continue
            oferta = _oferta(regra, product, link)
            if oferta is None:
                continue
            resultado[product.pk] = oferta
            break
    return resultado


def oferta_para(product, restaurant_id=None):
    """A oferta de um produto só. Respeita o que a listagem já resolveu.

    `_oferta_resolvida` é o cache que a listagem deixa no objeto — o mesmo
    truque de `Command.em_uso` com a anotação. Sem ele, o serializer de trinta
    produtos resolveria trinta vezes a mesma disputa.
    """
    if product is None:
        return None
    if hasattr(product, "_oferta_resolvida"):
        return product._oferta_resolvida
    return ofertas_para([product], restaurant_id=restaurant_id).get(product.pk)


def primar(products, restaurant_id=None):
    """Resolve a lista de uma vez e pendura a resposta em cada produto."""
    ofertas = ofertas_para(products, restaurant_id=restaurant_id)
    for product in products:
        product._oferta_resolvida = ofertas.get(product.pk)
    return products
