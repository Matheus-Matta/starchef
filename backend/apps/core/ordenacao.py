"""Ordenar pela coluna que a tela mostra — em TODOS os registros, não na página.

Cada lista declarava poucos `ordering_fields`. Clicar em "Cliente" mandava
`?ordering=customer_name`, o `OrderingFilter` do DRF descartava em silêncio o
que não estava na lista, e a tabela reordenava só as linhas da página: o "Z" da
página 1 vinha antes do "A" da página 2.

Agora vale também a coluna que o serializer MOSTRA e que tem campo no banco:
`customer_name` (source `customer.name`) ordena por `customer__name`; uma
chave estrangeira ordena pelo nome do registro, não pelo id. Coluna calculada
(`SerializerMethodField`) não tem como ser ordenada pelo banco — a view pode
dizer o caminho em `ordenacao_das_colunas`, senão ela fica de fora.

Só o que a lista já mostra: campo fora do serializer (a senha do usuário)
continua sem ordenação, porque ordenar por ele revelaria o que não se vê.
"""
from django.core.exceptions import FieldDoesNotExist
from rest_framework.filters import OrderingFilter

#: Como uma chave estrangeira aparece na tela, em ordem de preferência.
NOMES_DE_EXIBICAO = ("name", "trade_name", "number", "code", "username", "title")


def _campo(modelo, nome):
    try:
        return modelo._meta.get_field(nome)
    except FieldDoesNotExist:
        return None


def caminho_no_banco(modelo, fonte):
    """`customer.name` → `customer__name`; `None` se não for campo do banco."""
    partes, caminho = fonte.split("."), []
    for posicao, parte in enumerate(partes):
        campo = _campo(modelo, parte)
        if campo is None or campo.many_to_many or campo.one_to_many:
            return None
        if campo.get_internal_type() == "JSONField":
            return None
        caminho.append(campo.name)
        ultima = posicao == len(partes) - 1
        if not campo.is_relation:
            return "__".join(caminho) if ultima else None
        modelo = campo.related_model
        if ultima:
            exibido = next((n for n in NOMES_DE_EXIBICAO if _campo(modelo, n)), None)
            return "__".join([*caminho, exibido]) if exibido else None
    return None


def colunas_ordenaveis(view, queryset):
    """{coluna da tela: caminho no banco} que esta lista sabe ordenar."""
    declarados = getattr(view, "ordering_fields", None) or []
    mapa = {nome: nome for nome in declarados if declarados != "__all__"}
    mapa.update(getattr(view, "ordenacao_das_colunas", None) or {})
    anotacoes = set(queryset.query.annotations)
    try:
        campos = view.get_serializer().fields
    except Exception:  # noqa: BLE001 — sem serializer, valem só os declarados
        campos = {}
    for nome, campo in campos.items():
        if nome in mapa or getattr(campo, "write_only", False):
            continue
        fonte = getattr(campo, "source", None) or nome
        if fonte == "*":
            continue
        if fonte in anotacoes:
            mapa[nome] = fonte
        elif caminho := caminho_no_banco(queryset.model, fonte):
            mapa[nome] = caminho
    return mapa


class OrdenacaoPorColuna(OrderingFilter):
    """O `OrderingFilter` do DRF, aceitando as colunas da tela (ver o módulo)."""

    def get_ordering(self, request, queryset, view):
        pedido = request.query_params.get(self.ordering_param)
        if not pedido:
            return self.get_default_ordering(view)
        mapa = colunas_ordenaveis(view, queryset)
        termos = []
        for termo in (t.strip() for t in pedido.split(",")):
            caminho = mapa.get(termo.lstrip("-"))
            if caminho and termo.lstrip("-"):
                termos.append(f"-{caminho}" if termo.startswith("-") else caminho)
        if not termos:
            return self.get_default_ordering(view)
        # Desempate pelo id: com "status" repetido em vinte linhas, a paginação
        # por OFFSET mostrava o mesmo pedido em duas páginas e sumia com outro.
        return [*termos, "-pk" if termos[0].startswith("-") else "pk"]
