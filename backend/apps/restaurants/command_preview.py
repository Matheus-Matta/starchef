"""O resumo do que cada comanda da página tem, para o cartão mostrar de passagem.

O app do garçom desenha a grade e mostra, em cada cartão, "3x X-Burger ·
1x Refrigerante". Sem isto ele teria de abrir comanda por comanda. Aqui é UMA
consulta para a página inteira, e só quando pedida (`?preview=1`): o PDV e o
painel não usam o resumo e não pagam por ele.

O nome é o do CADASTRO do produto, o mesmo do cardápio. As mesmas regras de
"o que está a cobrar" da contagem (`billable_items_of`): pendente, não
cancelado, não cortesia, não apagado.
"""
from decimal import Decimal

from rest_framework.response import Response

#: Linhas por cartão. O resto vira "+N": o cartão é uma olhada, não a conta.
LIMITE = 4


def resumo_dos_itens(command_ids):
    """`{command_id: {"items": [...], "more": n}}` para as comandas pedidas.

    O mesmo produto lançado em rodadas diferentes vira UMA linha somada — duas
    linhas de "X-Burger" num cartão pequeno gastam o espaço de outro prato.
    """
    from apps.orders.command_billing import billable_items_of

    ids = list(command_ids)
    agrupado = {str(pk): {} for pk in ids}
    linhas = (
        billable_items_of(ids)
        .prefetch_related(None)
        .values_list("command_id", "product_id", "product__name", "product__pricing_unit", "quantity")
    )
    for command_id, product_id, nome, unidade, quantidade in linhas:
        por_produto = agrupado[str(command_id)]
        linha = por_produto.setdefault(product_id, {"name": nome, "unit": unidade, "q": Decimal(0)})
        linha["q"] += quantidade
    return {
        command_id: {
            "items": [
                {"name": linha["name"], "quantity": _texto(linha["q"]), "unit": linha["unit"]}
                for linha in list(por_produto.values())[:LIMITE]
            ],
            "more": max(len(por_produto) - LIMITE, 0),
        }
        for command_id, por_produto in agrupado.items()
    }


def _texto(quantidade):
    """`3`, e não `3.000`; `0.35` para o quilo."""
    normal = quantidade.normalize()
    return format(normal, "f") if normal == normal.to_integral() else str(normal)


class ResumoDosItensMixin:
    """`?preview=1` na listagem: cada linha ganha `pending_preview`."""

    def list(self, request, *args, **kwargs):
        if str(request.query_params.get("preview") or "").lower() not in {"1", "true", "yes"}:
            return super().list(request, *args, **kwargs)
        queryset = self.filter_queryset(self.get_queryset())
        pagina = self.paginate_queryset(queryset)
        objetos = list(pagina if pagina is not None else queryset)
        contexto = self.get_serializer_context()
        contexto["resumo_dos_itens"] = resumo_dos_itens(obj.pk for obj in objetos)
        dados = self.get_serializer_class()(objetos, many=True, context=contexto).data
        return self.get_paginated_response(dados) if pagina is not None else Response(dados)
