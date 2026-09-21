"""O contrato de rotas entre o backend e o app do garcom (`pdv_mobile/`).

Irmao de `test_contrato_pdv_desktop.py`, e pelo mesmo motivo: o aplicativo
monta a URL como TEXTO, entao renomear uma rota aqui nao quebra compilacao
nenhuma do lado dele. O defeito so aparece quando o garcom executa AQUELE
gesto, no meio do salao, e a mensagem na tela fala do assunto da tela ("nao foi
possivel lancar o item"), nao da URL.

O app do garcom tem um agravante sobre o desktop: ele guarda o gesto numa FILA
OFFLINE. Uma rota que nao existe mais nao falha na hora — ela falha quando a
fila sobe, horas depois, com o garcom ja em casa e o lancamento perdido.

A lista abaixo e extraida de `pdv_mobile/lib/**.dart` (todo caminho literal de
chamada). Ao mexer numa rota, este teste falha ANTES de alguem descobrir no
salao.
"""

import pytest
from django.urls import Resolver404, resolve

pytestmark = pytest.mark.django_db

_UUID = "8820fb83-a532-472d-84f9-6aa5bd65c059"

ROTAS_DO_APP = [
    ("POST", "/auth/login/"),
    ("POST", "/auth/refresh/"),
    ("GET", "/cash-register/current/"),
    ("GET", "/commands/"),
    # A COMANDA COMO BLOCO DE NOTAS. O garcom anota no cartao e manda para a
    # producao; nenhum pedido e aberto. Estas tres substituiram `open-command`.
    ("GET", "/commands/{id}/items/"),
    ("POST", "/commands/{id}/items/"),
    ("DELETE", "/commands/{id}/items/{id}/void/"),
    ("POST", "/commands/{id}/send-to-kitchen/"),
    ("POST", "/commands/{id}/link-table/"),
    ("POST", "/commands/{id}/unlink-table/"),
    ("GET", "/menu/products/"),
    ("GET", "/orders/"),
    ("GET", "/orders/{id}/"),
    ("POST", "/orders/create-with-item/"),
    ("POST", "/orders/{id}/items/"),
    ("DELETE", "/orders/{id}/items/{id}/void/"),
    ("POST", "/orders/{id}/pay/"),
    ("GET", "/orders/{id}/payments/"),
    ("POST", "/orders/{id}/send-to-kitchen/"),
    ("GET", "/payments/methods/"),
    ("GET", "/print-jobs/"),
    ("POST", "/print-jobs/{id}/claim/"),
    ("POST", "/print-jobs/{id}/mark-failed/"),
    ("POST", "/print-jobs/{id}/mark-printed/"),
    ("POST", "/print-jobs/{id}/release/"),
    ("GET", "/printers/"),
    ("GET", "/tables/"),
]


@pytest.mark.parametrize("metodo,rota", ROTAS_DO_APP, ids=lambda v: str(v))
def test_rota_do_app_do_garcom_existe_e_aceita_o_metodo(metodo, rota):
    caminho = "/api/v1" + rota.replace("{id}", _UUID)
    try:
        correspondencia = resolve(caminho)
    except Resolver404:
        pytest.fail(
            f"O app do garcom chama {metodo} {caminho}, e esta rota nao existe. "
            f"Se ela foi renomeada, ajuste tambem pdv_mobile/lib/."
        )

    view = correspondencia.func
    # ViewSet do DRF: `initkwargs['actions']` mapeia metodo -> action.
    acoes = getattr(view, "actions", None)
    if acoes is None:
        acoes = getattr(view, "initkwargs", {}).get("actions")
    if acoes is None:
        # APIView simples (login/refresh): o roteamento nao declara acoes, e o
        # metodo e conferido pela propria classe.
        return
    assert metodo.lower() in acoes, (
        f"O app do garcom chama {metodo} {caminho}, mas esta rota so aceita "
        f"{sorted(m.upper() for m in acoes)}. Um metodo errado vira 405, e o "
        f"gesto fica preso na fila offline ate alguem olhar."
    )
