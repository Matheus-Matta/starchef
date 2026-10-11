"""Nada que chega é descartado em silêncio: o que foi ignorado vai ao histórico.

Loja e nuvem aceitam escrever, e quem decide é a versão: o mais novo vence, o
mais velho é ignorado. Ignorar é o certo — mas jogar fora sem registro tirava
a chance de recuperar um dado que alguém digitou (um recebimento, uma
anotação). `SyncDiscard` guarda o que chegou, por que foi ignorado e as duas
versões; nada nele é usado pela operação.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.synchronization.models import SyncDiscard
from apps.synchronization.tests.test_anotacao_cobrada_nos_dois_lados import (  # noqa: F401 — fixture
    _item_chega_da_nuvem, cobrada_na_loja,
)
from apps.synchronization.tests.test_versao_mais_nova_vence import (  # noqa: F401 — fixture
    _entregar, _payload, grupo,
)

pytestmark = pytest.mark.django_db


def test_versao_mais_velha_da_sincronizacao_vai_ao_historico(
    como_loja, conta, no_nuvem, no_loja, grupo  # noqa: F811
):
    novo = timezone.now() + timedelta(minutes=5)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=novo, name="Nova"))
    _entregar(conta, no_nuvem, no_loja,
              _payload(grupo, no_nuvem, quando=novo - timedelta(minutes=1), name="Velha"))

    descarte = SyncDiscard.objects.get(entity_type="customer_group", entity_id=str(grupo.pk))
    assert descarte.motivo == SyncDiscard.MOTIVO_VERSAO_MAIS_VELHA
    assert descarte.origem == SyncDiscard.ORIGEM_SYNC
    assert descarte.dados["name"] == "Velha"
    assert descarte.versao_local > descarte.versao_recebida
    assert descarte.event_id is not None


def test_anotacao_que_perdeu_o_vinculo_vai_ao_historico(
    conta, no_nuvem, no_loja, cobrada_na_loja  # noqa: F811
):
    item_da_loja, pedido_da_nuvem, anotacao = cobrada_na_loja
    _item_chega_da_nuvem(conta, no_nuvem, no_loja, item_da_loja, pedido_da_nuvem,
                         timezone.now() + timedelta(minutes=1))

    descarte = SyncDiscard.objects.get(motivo=SyncDiscard.MOTIVO_ANOTACAO_PERDEU_VINCULO)
    assert descarte.entity_id == str(item_da_loja.pk)
    assert descarte.dados["command_item_id"] == str(anotacao.pk)


def test_o_comando_exporta_o_que_chegou_para_recuperar(
    como_loja, conta, no_nuvem, no_loja, grupo  # noqa: F811
):
    import io
    import json

    from django.core.management import call_command

    novo = timezone.now() + timedelta(minutes=5)
    _entregar(conta, no_nuvem, no_loja, _payload(grupo, no_nuvem, quando=novo, name="Nova"))
    _entregar(conta, no_nuvem, no_loja,
              _payload(grupo, no_nuvem, quando=novo - timedelta(minutes=1), name="Velha"))
    saida = io.StringIO()

    call_command("sync_descartes", "--id", str(grupo.pk), "--json", stdout=saida)

    [exportado] = json.loads(saida.getvalue())
    assert exportado["motivo"] == "versao_mais_velha" and exportado["dados"]["name"] == "Velha"
