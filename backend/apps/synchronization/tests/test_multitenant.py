"""Isolamento por conta e autenticação do nó (§23.1, §23.5).

O teste mais importante do conjunto: conta A nunca vê conta B, e o payload
nunca é prova de autorização.
"""
import uuid

import pytest

from apps.synchronization.constants import NodeStatus, NodeType, PROTOCOL_VERSION
from apps.synchronization.models import SyncNode
from apps.synchronization.services import authentication, crypto, inbox, nodes
from apps.synchronization.tests.conftest import TOKEN_DE_TESTE

pytestmark = pytest.mark.django_db


def _hello(no, **extra):
    base = {
        "node_id": str(no.id),
        "pair_id": str(no.pair_id),
        "account_id": str(no.account_id),
        "environment": no.environment,
        "protocol_version": PROTOCOL_VERSION,
        "schema_version": 1,
        "app_version": "3.0.0",
    }
    base.update(extra)
    return base


def test_token_valido_autentica(como_nuvem, no_loja):
    autenticado = authentication.authenticate(_hello(no_loja), raw_token=TOKEN_DE_TESTE)
    assert autenticado.id == no_loja.id
    assert autenticado.status == NodeStatus.ACTIVE


def test_token_invalido_e_recusado(como_nuvem, no_loja):
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(_hello(no_loja), raw_token="token-errado")


def test_no_revogado_nao_conecta(como_nuvem, no_loja):
    no_loja.status = NodeStatus.REVOKED
    no_loja.is_active = False
    no_loja.save()
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(_hello(no_loja), raw_token=TOKEN_DE_TESTE)


def test_conta_adulterada_no_hello_e_recusada(como_nuvem, no_loja, outra_conta):
    payload = _hello(no_loja, account_id=str(outra_conta.id))
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(payload, raw_token=TOKEN_DE_TESTE)


def test_pair_id_adulterado_e_recusado(como_nuvem, no_loja):
    payload = _hello(no_loja, pair_id=str(uuid.uuid4()))
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(payload, raw_token=TOKEN_DE_TESTE)


def test_ambiente_fora_de_development_e_recusado(como_nuvem, no_loja):
    payload = _hello(no_loja, environment="production")
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(payload, raw_token=TOKEN_DE_TESTE)


def test_protocolo_incompativel_e_recusado(como_nuvem, no_loja):
    payload = _hello(no_loja, protocol_version=99)
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(payload, raw_token=TOKEN_DE_TESTE)


def test_ip_fora_da_lista_e_recusado(como_nuvem, no_loja):
    no_loja.allowed_ip = "10.0.0.1"
    no_loja.save()
    with pytest.raises(authentication.AuthenticationFailed):
        authentication.authenticate(_hello(no_loja), raw_token=TOKEN_DE_TESTE, client_ip="10.0.0.9")


def test_evento_com_conta_de_outro_e_rejeitado(como_nuvem, conta, outra_conta, no_loja, no_nuvem):
    """O account_id do envelope não autoriza nada. Só a conexão autentica."""
    bruto = {
        "event_id": str(uuid.uuid4()),
        "account_id": str(outra_conta.id),  # <- adulterado
        "target_node_id": str(no_nuvem.id),
        "sequence": 1,
        "entity_type": "restaurant",
        "entity_id": str(uuid.uuid4()),
        "operation": "UPSERT",
        "payload": {"fields": {}},
    }
    with pytest.raises(inbox.CrossTenantRejected):
        inbox.store_batch([bruto], connection_node=no_loja, account_id=conta.id)


def test_lote_repetido_nao_duplica_na_inbox(como_nuvem, conta, no_loja, no_nuvem):
    payload = {"fields": {"trade_name": "X"}}
    bruto = {
        "event_id": str(uuid.uuid4()),
        "account_id": str(conta.id),
        "target_node_id": str(no_nuvem.id),
        "sequence": 1,
        "entity_type": "restaurant",
        "entity_id": str(uuid.uuid4()),
        "operation": "UPSERT",
        "payload": payload,
        "payload_checksum": crypto.checksum(payload),
    }
    primeiros, _, _ = inbox.store_batch([bruto], connection_node=no_loja, account_id=conta.id)
    repetidos, _, _ = inbox.store_batch([bruto], connection_node=no_loja, account_id=conta.id)
    assert len(primeiros) == 1
    assert len(repetidos) == 0  # deduplicado por event_id


def test_a_nuvem_so_envia_para_os_nos_da_propria_conta(como_nuvem, conta, outra_conta, no_loja):
    """targets_for filtra por conta. Sem isso, a conta A receberia da B."""
    vizinho = SyncNode.objects.create(
        pair_id=uuid.uuid4(), account=outra_conta, node_type=NodeType.LOCAL,
        name="Loja da outra conta", status=NodeStatus.ACTIVE,
    )
    destinos = nodes.targets_for(nodes.self_node(), conta.id)
    ids = {n.id for n in destinos}
    assert no_loja.id in ids
    assert vizinho.id not in ids
