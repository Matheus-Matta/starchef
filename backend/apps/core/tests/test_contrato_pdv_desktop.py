"""O contrato de rotas entre o backend e o PDV Desktop (`pdv_desktop/`).

Este backend e compartilhado: web, PDV antigo, app do garcom e o PDV Desktop.
Renomear uma rota aqui nao quebra compilacao nenhuma do lado do PDV — ele monta
a URL como texto. O defeito so aparece quando o operador executa AQUELE gesto,
e a mensagem na tela fala do assunto da tela ("o comprovante nao saiu na
impressora"), nao da URL. Foi assim que `/cash-registers/` e `/products/`
chegaram a rodar: duas rotas que este backend nunca teve.

A lista abaixo e extraida de `pdv_desktop/lib/**.dart` (toda chamada
`api.get/post/patch/delete` com caminho literal). Ao mexer numa rota, este
teste falha ANTES de alguem descobrir no balcao.
"""

import pytest
from django.urls import Resolver404, resolve

pytestmark = pytest.mark.django_db

_UUID = "8820fb83-a532-472d-84f9-6aa5bd65c059"

# (metodo, caminho). `{id}` vira um UUID qualquer: o que se testa e a rota
# existir e aceitar o metodo, nao o registro existir.
ROTAS_DO_PDV = [
    ("POST", "/auth/login/"),
    ("GET", "/auth/me/"),
    ("POST", "/auth/refresh/"),
    ("GET", "/cash-register/current/"),
    ("POST", "/cash-register/open/"),
    ("POST", "/cash-register/{id}/approve/"),
    ("POST", "/cash-register/{id}/close/"),
    ("POST", "/cash-register/{id}/supply/"),
    ("POST", "/cash-register/{id}/withdrawal/"),
    ("GET", "/cash-register/{id}/print-document/"),
    ("GET", "/cash-stations/"),
    ("GET", "/commands/"),
    ("GET", "/commands/by-code/"),
    ("POST", "/commands/{id}/link-table/"),
    ("POST", "/commands/{id}/unlink-table/"),
    ("GET", "/customers/"),
    ("POST", "/customers/"),
    ("POST", "/invoices/emit/"),
    ("POST", "/invoices/{id}/print/"),
    ("POST", "/invoices/{id}/refresh-status/"),
    ("GET", "/menu/categories/"),
    ("GET", "/menu/products/"),
    ("GET", "/orders/"),
    ("POST", "/orders/"),
    ("POST", "/orders/open-command/"),
    ("GET", "/orders/{id}/"),
    ("DELETE", "/orders/{id}/"),
    ("POST", "/orders/{id}/cancel/"),
    ("POST", "/orders/{id}/close/"),
    ("POST", "/orders/{id}/items/"),
    ("POST", "/orders/{id}/items/{id}/quantity/"),
    ("DELETE", "/orders/{id}/items/{id}/void/"),
    ("POST", "/orders/{id}/pay/"),
    ("GET", "/orders/{id}/payments/"),
    ("DELETE", "/orders/{id}/payments/{id}/"),
    ("POST", "/orders/{id}/print/"),
    ("POST", "/orders/{id}/send-to-kitchen/"),
    ("GET", "/payments/methods/"),
    ("GET", "/print-jobs/"),
    ("GET", "/print-jobs/{id}/"),
    ("POST", "/print-jobs/{id}/claim/"),
    ("POST", "/print-jobs/{id}/release/"),
    ("POST", "/print-jobs/{id}/mark-failed/"),
    ("POST", "/print-jobs/{id}/mark-printed/"),
    ("POST", "/print-jobs/{id}/requeue/"),
    ("GET", "/printers/"),
    ("GET", "/printers/templates/"),
    ("POST", "/printers/{id}/test-connection/"),
    ("GET", "/restaurants/"),
    ("GET", "/restaurants/{id}/cash-auth/"),
    ("GET", "/scales/"),
    ("PATCH", "/scales/{id}/"),
    ("GET", "/scales/readings/"),
    ("POST", "/scales/readings/"),
    ("POST", "/scales/{id}/checkout-command/"),
    ("GET", "/scales/{id}/latest-reading/"),
    ("GET", "/tables/"),
    ("GET", "/tables/sectors/"),
    ("POST", "/tables/{id}/transfer-commands/"),
]


@pytest.mark.parametrize("metodo,rota", ROTAS_DO_PDV, ids=lambda v: str(v))
def test_rota_do_pdv_existe_e_aceita_o_metodo(metodo, rota):
    caminho = "/api/v1" + rota.replace("{id}", _UUID)
    try:
        correspondencia = resolve(caminho)
    except Resolver404:
        pytest.fail(
            f"O PDV Desktop chama {metodo} {caminho}, e esta rota nao existe. "
            f"Se ela foi renomeada, ajuste tambem pdv_desktop/lib/."
        )

    view = correspondencia.func
    # ViewSet do DRF: `initkwargs['actions']` mapeia metodo -> action.
    acoes = getattr(view, "actions", None)
    if acoes is None:
        acoes = getattr(view, "initkwargs", {}).get("actions")
    if acoes is None:
        # APIView simples (login/refresh/me): o roteamento nao declara acoes, e
        # o metodo e conferido pela propria classe.
        return
    assert metodo.lower() in acoes, (
        f"O PDV Desktop chama {metodo} {caminho}, mas esta rota so aceita "
        f"{sorted(m.upper() for m in acoes)}. Um metodo errado vira 405, e a "
        f"tela do operador mostra o assunto dela — nao o metodo."
    )
