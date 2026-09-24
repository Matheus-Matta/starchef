"""O numero do pedido sob disputa — e o erro que o operador nao podia ver.

`next_order_sequence` e `Max + 1` lido SEM TRAVA. Entre a leitura e a gravacao
cabe outra escrita: outro caixa abrindo conta no mesmo instante, ou a
sincronizacao trazendo do outro no um pedido que ocupa aquele numero.

O modo de falhar era ruim de um jeito especifico: o banco recusava (certo — a
restricao existe para isso) e o operador via "Ja existe um registro com estes
dados (valor duplicado)" numa tela que dizia "Nao foi possivel abrir o
pedido". A frase nao diz o que ele fez, nem em que registro, nem o que fazer.
Ele repetia o gesto e recebia a mesma coisa.
"""
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.orders.models import Order
from apps.orders.services import create_order

pytestmark = pytest.mark.django_db


def test_numero_tomado_no_meio_do_caminho_e_renumerado(
    restaurant, branch, manager_user, monkeypatch
):
    """O caso real: o numero escolhido ja pertence a outro pedido.

    O pedido e gravado COM filial de proposito. A restricao
    `unique_order_sequence_by_branch` cobre `(branch, sequence)`, e nos dois
    bancos uma coluna nula nunca conflita com outra nula — com `branch=None`,
    que e como `create_order` grava hoje, a restricao simplesmente nao vale.
    O que este teste prova e o retry: quando a restricao VALE, a disputa pelo
    numero se resolve renumerando, e nao estourando na cara do operador.
    """
    from apps.orders import order_numbering

    # O outro no ja gravou o numero 7 nesta filial — e o que a sincronizacao
    # faz ao trazer um pedido do outro lado. Fora da transacao de proposito:
    # dentro dela o rollback do savepoint desfaria o conflito junto.
    Order.objects.create(
        account=restaurant.account, restaurant=restaurant, branch=branch,
        sequence=7, order_type=Order.TYPE_COUNTER,
        created_by=manager_user, updated_by=manager_user,
    )

    escolhas = iter([7, 8])
    chamadas = {"n": 0}

    def sequencia_disputada(_rest):
        chamadas["n"] += 1
        return next(escolhas)

    monkeypatch.setattr(order_numbering, "next_order_sequence", sequencia_disputada)

    pedido = order_numbering._criar_pedido_numerado(
        account=restaurant.account, restaurant=restaurant, branch=branch,
        order_type=Order.TYPE_COUNTER,
        created_by=manager_user, updated_by=manager_user,
    )

    # Renumerou em silencio: o operador nem soube que houve disputa.
    assert chamadas["n"] == 2
    assert pedido.sequence == 8
    assert Order.all_objects.filter(branch=branch, sequence=7).count() == 1


def test_outra_violacao_NAO_e_repetida(restaurant, branch, manager_user, monkeypatch):
    """Repetir uma escrita que fere OUTRA regra so multiplicaria o erro.

    Um erro claro viraria seis tentativas e a mesma falha no fim — com o
    tempo do operador gasto no meio.
    """
    from apps.orders import order_numbering

    def sempre_falha(rest):
        raise IntegrityError('null value in column "restaurant_id"')

    monkeypatch.setattr(order_numbering, "next_order_sequence", sempre_falha)

    with pytest.raises(IntegrityError):
        create_order(
            restaurant=restaurant, branch=branch,
            order_type=Order.TYPE_COUNTER, user=manager_user,
        )


def test_disputa_sem_fim_explica_a_causa_provavel(
    restaurant, branch, manager_user, monkeypatch
):
    """Desistir tambem precisa ensinar: numero sempre tomado = faixas iguais."""
    from apps.orders import order_numbering

    def sempre_colide(rest):
        raise IntegrityError(
            'duplicate key value violates unique constraint '
            '"unique_order_sequence_by_branch"'
        )

    monkeypatch.setattr(order_numbering, "next_order_sequence", sempre_colide)

    with pytest.raises(ValidationError) as falha:
        create_order(
            restaurant=restaurant, branch=branch,
            order_type=Order.TYPE_COUNTER, user=manager_user,
        )

    recado = " ".join(falha.value.messages)
    assert "SYNC_NODE_TYPE" in recado
    assert "nenhum pedido foi aberto" in recado.lower()


def test_a_mensagem_de_conflito_diz_qual_conflito():
    """"Valor duplicado" nao diz o que o operador fez nem o que fazer."""
    from apps.core.exceptions import _integrity_message

    numero = _integrity_message(IntegrityError(
        'duplicate key value violates unique constraint '
        '"unique_order_sequence_by_branch"'
    ))
    assert "numero de pedido" in numero.lower().replace("ú", "u")
    assert "SYNC_NODE_TYPE" in numero

    anotacao = _integrity_message(IntegrityError(
        'UNIQUE constraint failed: index "unique_order_item_per_command_item"'
    ))
    assert "cart" in anotacao.lower()

    # O que nao esta no catalogo continua caindo na frase geral.
    generico = _integrity_message(IntegrityError("UNIQUE constraint failed: x.y"))
    assert "valor duplicado" in generico.lower()
