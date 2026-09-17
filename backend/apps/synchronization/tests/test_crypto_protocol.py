"""Segurança do transporte: token, chave, envelope e adulteração (§23.5)."""
import pytest

from apps.synchronization.constants import MessageType
from apps.synchronization.services import crypto, protocol


def test_token_e_hash_sao_coisas_diferentes():
    token = crypto.generate_token()
    assert crypto.token_matches(token, crypto.hash_token(token))
    assert not crypto.token_matches("outro-token", crypto.hash_token(token))
    # O hash não volta a ser o token: é esse o ponto do §8.1.
    assert crypto.hash_token(token) != token


def test_chave_de_32_bytes_e_fingerprint_estavel():
    chave = crypto.generate_key()
    assert len(crypto.load_key(chave)) == 32
    assert crypto.fingerprint(chave) == crypto.fingerprint(chave)
    assert crypto.fingerprint(chave) != crypto.fingerprint(crypto.generate_key())


def test_chave_de_tamanho_errado_e_recusada():
    with pytest.raises(ValueError, match="32 bytes"):
        crypto.load_key("dG9vLWN1cnRv")


def test_nonce_nunca_se_repete():
    chave = crypto.generate_key()
    nonces = {crypto.encrypt({"a": 1}, chave)[0] for _ in range(50)}
    assert len(nonces) == 50


def test_ida_e_volta_do_envelope_cifrado():
    chave = crypto.generate_key()
    envelope = protocol.build(
        MessageType.EVENT_BATCH,
        source_node_id="11111111-1111-1111-1111-111111111111",
        target_node_id="22222222-2222-2222-2222-222222222222",
        account_id="33333333-3333-3333-3333-333333333333",
        payload={"events": [{"id": 1}]},
        key=chave,
        key_id="dev-key-01",
    )
    assert "ciphertext" in envelope and "payload" not in envelope
    assert protocol.parse(envelope, chave) == {"events": [{"id": 1}]}


def test_ciphertext_alterado_nao_decifra():
    chave = crypto.generate_key()
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=None, target_node_id=None,
        account_id=None, payload={"x": 1}, key=chave,
    )
    envelope["ciphertext"] = "AAAA" + envelope["ciphertext"][4:]
    with pytest.raises(protocol.ProtocolError):
        protocol.parse(envelope, chave)


def test_trocar_o_destinatario_invalida_a_tag():
    """O cabeçalho entra como dado autenticado: mexer nele quebra o AES-GCM."""
    chave = crypto.generate_key()
    envelope = protocol.build(
        MessageType.EVENT_BATCH,
        source_node_id="11111111-1111-1111-1111-111111111111",
        target_node_id="22222222-2222-2222-2222-222222222222",
        account_id="33333333-3333-3333-3333-333333333333",
        payload={"x": 1}, key=chave,
    )
    envelope["target_node_id"] = "99999999-9999-9999-9999-999999999999"
    with pytest.raises(protocol.ProtocolError):
        protocol.parse(envelope, chave)


def test_checksum_divergente_e_recusado():
    envelope = protocol.build(
        MessageType.EVENT_BATCH, source_node_id=None, target_node_id=None,
        account_id=None, payload={"x": 1},
    )
    envelope["payload"] = {"x": 2}
    with pytest.raises(protocol.ProtocolError, match="Checksum"):
        protocol.parse(envelope)


def test_versao_de_protocolo_incompativel():
    envelope = protocol.build(
        MessageType.HEARTBEAT, source_node_id=None, target_node_id=None,
        account_id=None, payload={},
    )
    envelope["protocol_version"] = 99
    with pytest.raises(protocol.ProtocolError, match="incompatível"):
        protocol.parse(envelope)


def test_checksum_e_estavel_independente_da_ordem_das_chaves():
    assert crypto.checksum({"a": 1, "b": 2}) == crypto.checksum({"b": 2, "a": 1})
