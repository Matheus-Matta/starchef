"""A chave AES é do AMBIENTE, e as duas pontas precisam ter a mesma.

Este arquivo existe por causa de um bug que passou por 181 testes: o
provisionamento gerava `crypto.generate_key()` — uma chave NOVA por nó — e a
entregava à loja no pacote de matrícula. Só que o consumer da nuvem cifra com
`settings.SYNC_ENCRYPTION_KEY`, o dela.

Resultado: duas chaves diferentes, toda mensagem falhando na tag do AES-GCM, e
nada chegando ao domínio. Nenhum teste viu, porque todos rodam com a MESMA
chave nos dois lados (mesmo processo, mesma `settings`) — o defeito morava
exatamente na costura que os testes curto-circuitavam.

A regra, do §8.4 do plano: **uma chave por ambiente**, em variável de ambiente.
O banco guarda só o `key_id` e a impressão digital, e é para isso que a
impressão digital serve — conferir que as duas pontas têm a mesma chave.
"""
import pytest

from apps.synchronization.constants import MessageType
from apps.synchronization.services import crypto, protocol, provisioning

pytestmark = pytest.mark.django_db


def _mensagem(chave):
    return protocol.build(
        MessageType.EVENT_BATCH, source_node_id=None, target_node_id=None,
        account_id=None, payload={"events": [{"x": 1}]}, key=chave,
    )


def test_o_pacote_entrega_a_chave_DO_AMBIENTE(settings, como_nuvem, conta):
    """O que a loja recebe tem de ser exatamente o que a nuvem usa."""
    chave_da_nuvem = crypto.generate_key()
    settings.SYNC_ENCRYPTION_KEY = chave_da_nuvem
    settings.SYNC_ENCRYPTION_KEY_ID = "dev-key-01"

    _no, pacote = provisioning.provision_local_node(
        account=conta, name="Loja X", cloud_endpoint="wss://n.test/ws/sync/v1/"
    )

    assert pacote["SYNC_ENCRYPTION_KEY"] == chave_da_nuvem
    assert pacote["SYNC_ENCRYPTION_KEY_ID"] == "dev-key-01"


def test_a_loja_decifra_o_que_a_nuvem_cifrou(settings, como_nuvem, conta):
    """O teste de ponta a ponta que o bug atravessava."""
    settings.SYNC_ENCRYPTION_KEY = crypto.generate_key()
    _no, pacote = provisioning.provision_local_node(
        account=conta, name="Loja Y", cloud_endpoint="wss://n.test/ws/sync/v1/"
    )

    # A nuvem cifra com a chave dela; a loja usa a que veio no pacote.
    envelope = _mensagem(settings.SYNC_ENCRYPTION_KEY)
    assert protocol.parse(envelope, pacote["SYNC_ENCRYPTION_KEY"]) == {"events": [{"x": 1}]}


def test_chaves_diferentes_falham_sempre(settings, como_nuvem, conta):
    """A prova de que o bug antigo seria fatal, e não só degradado."""
    envelope = _mensagem(crypto.generate_key())
    with pytest.raises(protocol.ProtocolError, match="decifrar"):
        protocol.parse(envelope, crypto.generate_key())


def test_a_impressao_digital_confere_as_duas_pontas(settings, como_nuvem, conta):
    """`secret_fingerprint` existe para isto: comparar sem guardar a chave."""
    settings.SYNC_ENCRYPTION_KEY = crypto.generate_key()
    no, pacote = provisioning.provision_local_node(
        account=conta, name="Loja Z", cloud_endpoint="wss://n.test/ws/sync/v1/"
    )

    assert no.secret_fingerprint == crypto.fingerprint(pacote["SYNC_ENCRYPTION_KEY"])
    # E a chave pura NÃO fica no banco.
    assert pacote["SYNC_ENCRYPTION_KEY"] not in (no.secret_fingerprint, no.credential_hash)


def test_rotacionar_troca_o_token_e_preserva_a_chave(settings, como_nuvem, conta):
    """Rotação é do token, por nó. Trocar a chave aqui quebraria a loja."""
    settings.SYNC_ENCRYPTION_KEY = crypto.generate_key()
    no, primeiro = provisioning.provision_local_node(
        account=conta, name="Loja W", cloud_endpoint="wss://n.test/ws/sync/v1/"
    )

    segundo = provisioning.rotate_credentials(no)

    assert segundo["SYNC_AUTH_TOKEN"] != primeiro["SYNC_AUTH_TOKEN"]
    assert segundo["SYNC_ENCRYPTION_KEY"] == primeiro["SYNC_ENCRYPTION_KEY"]


def test_sem_chave_na_nuvem_a_loja_tambem_fica_sem(settings, como_nuvem, conta):
    """Modo em claro é válido — o que não pode é UMA ponta cifrar sozinha."""
    settings.SYNC_ENCRYPTION_KEY = ""
    no, pacote = provisioning.provision_local_node(
        account=conta, name="Loja V", cloud_endpoint="wss://n.test/ws/sync/v1/"
    )

    assert pacote["SYNC_ENCRYPTION_KEY"] == ""
    assert no.secret_fingerprint == ""

    # Os dois em claro conversam normalmente.
    envelope = _mensagem(None)
    assert protocol.parse(envelope, None) == {"events": [{"x": 1}]}


def test_uma_ponta_cifrando_e_a_outra_nao_falha(settings, como_nuvem):
    """O erro diz o que houve, em vez de devolver lixo."""
    envelope = _mensagem(crypto.generate_key())
    with pytest.raises(protocol.ProtocolError, match="sem chave configurada"):
        protocol.parse(envelope, None)
