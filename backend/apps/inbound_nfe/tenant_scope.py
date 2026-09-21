"""Qual restaurante o cliente pediu — e se ele pode.

A barra lateral da web manda `X-Restaurant-ID` em toda requisição, e estas
rotas o aceitam com precedência sobre o restaurante do perfil. Isso é
deliberado: um administrador troca de unidade pela barra lateral e a tela
inteira acompanha.

O que faltava era a conferência. Todas as consultas destas views já filtram por
`account=request.account`, então **não havia vazamento entre contas** — o
problema era DENTRO de uma conta: um operador preso ao restaurante A podia
mandar o id do B e disparar sincronização com a SEFAZ, mexer no NSU ou listar
notas dele.

`HasTenantAccess` não pega isso porque estas são `@action`s que não passam por
`get_object()`: a checagem de objeto nunca roda.

A resolução também vivia copiada em cinco lugares, cada cópia com uma variação
da cadeia de leitura. Duas delas liam `HTTP_X_RESTAURANT_ID` do `META`, duas
não — e `request.headers` já é insensível a maiúsculas, então as variações não
faziam diferença nenhuma além de esconder que eram a mesma coisa.
"""
from rest_framework.exceptions import PermissionDenied

from apps.core.access import is_tenant_admin


def _pedido_pelo_cliente(request):
    """O id que veio na requisição, em qualquer das três portas.

    `request.headers` é insensível a maiúsculas: `X-Restaurant-ID`,
    `x-restaurant-id` e `HTTP_X_RESTAURANT_ID` são a MESMA leitura.
    """
    bruto = (
        request.data.get("restaurant")
        if hasattr(request, "data") and hasattr(request.data, "get")
        else None
    )
    bruto = bruto or request.query_params.get("restaurant")
    bruto = bruto or request.headers.get("X-Restaurant-ID")
    valor = str(bruto or "").strip()
    return valor or None


def _do_perfil(request):
    perfil = getattr(request.user, "profile", None)
    return str(getattr(perfil, "restaurant_id", "") or "") or None


def restaurante_escolhido(request, *, cair_no_perfil=True):
    """O restaurante autorizado desta requisição, ou `None`.

    `None` significa "Todos os Restaurantes" — a visão consolidada da conta, e
    é por isso que ela existe como valor de retorno em vez de erro.

    Levanta `PermissionDenied` quando o cliente pede um restaurante que não é
    o dele. Administrador da conta troca de unidade à vontade; é o que a barra
    lateral faz.
    """
    pedido = _pedido_pelo_cliente(request)
    if not pedido:
        return _do_perfil(request) if cair_no_perfil else None

    if is_tenant_admin(request.user):
        return pedido

    proprio = _do_perfil(request)
    if proprio and pedido == proprio:
        return pedido

    raise PermissionDenied(
        "Você não tem acesso a este restaurante. Selecione uma unidade da qual "
        "você faz parte na barra lateral."
    )
