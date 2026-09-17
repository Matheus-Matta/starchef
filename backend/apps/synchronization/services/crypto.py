"""Token, hash, checksum e AES-256-GCM. Cada um com um papel só.

A confusão que este módulo evita é a do plano: *hash não descriptografa*. São
quatro coisas diferentes e elas nunca se misturam:

1. `generate_token()` — o segredo que o nó local apresenta para autenticar;
2. `hash_token()` — o que a nuvem guarda no banco (não dá para voltar);
3. `encrypt()/decrypt()` — AES-256-GCM sobre o payload, com chave de 32 bytes;
4. `fingerprint()` — SHA-256 da chave, só para conferir que os dois lados têm
   a mesma. Também não dá para voltar.
"""
import base64
import hashlib
import hmac
import json
import secrets

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32  # AES-256
NONCE_BYTES = 12  # tamanho recomendado para GCM


def generate_token():
    """O segredo em claro. Existe uma única vez, na tela de provisionamento."""
    return secrets.token_urlsafe(48)


def hash_token(raw_token):
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def token_matches(raw_token, stored_hash):
    """Comparação em tempo constante: um `==` aqui vaza o hash byte a byte."""
    if not raw_token or not stored_hash:
        return False
    return hmac.compare_digest(hash_token(raw_token), stored_hash)


def generate_key():
    """Chave AES de 32 bytes, em base64 — o formato que vai para a env."""
    return base64.b64encode(secrets.token_bytes(KEY_BYTES)).decode("ascii")


def load_key(encoded_key):
    """Aceita base64 (o formato padrão) ou 64 caracteres hexadecimais."""
    if not encoded_key:
        raise ValueError("Chave de criptografia vazia.")
    texto = encoded_key.strip()
    try:
        bruto = bytes.fromhex(texto) if len(texto) == 64 and _is_hex(texto) else base64.b64decode(texto)
    except Exception as erro:  # noqa: BLE001 — a mensagem importa mais que o tipo
        raise ValueError(f"Chave de criptografia inválida: {erro}") from erro
    if len(bruto) != KEY_BYTES:
        raise ValueError(f"A chave precisa ter {KEY_BYTES} bytes; recebeu {len(bruto)}.")
    return bruto


def _is_hex(texto):
    return all(c in "0123456789abcdefABCDEF" for c in texto)


def fingerprint(encoded_key):
    """SHA-256 da chave: serve para conferir, nunca para reconstruir."""
    return hashlib.sha256(load_key(encoded_key)).hexdigest()


def canonical_json(data):
    """A forma única de serializar antes de somar o checksum.

    Sem ordenação e sem separadores fixos, os dois lados calculam SHA-256
    diferentes para o MESMO conteúdo e toda mensagem vira NACK de checksum.
    """
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def checksum(data):
    fonte = data if isinstance(data, (bytes, bytearray)) else canonical_json(data).encode("utf-8")
    return hashlib.sha256(fonte).hexdigest()


def encrypt(payload, encoded_key, associated_data=None):
    """Cifra o payload. Devolve `(nonce_b64, ciphertext_b64)`.

    O nonce é sorteado a cada chamada — reutilizar nonce com a mesma chave em
    GCM quebra a cifra inteira, não só a mensagem repetida. `associated_data`
    (o envelope) entra na autenticação sem ser cifrada: trocar o destinatário
    no envelope invalida a tag.
    """
    chave = load_key(encoded_key)
    nonce = secrets.token_bytes(NONCE_BYTES)
    claro = canonical_json(payload).encode("utf-8")
    cifrado = AESGCM(chave).encrypt(nonce, claro, associated_data)
    return (
        base64.b64encode(nonce).decode("ascii"),
        base64.b64encode(cifrado).decode("ascii"),
    )


def decrypt(nonce_b64, ciphertext_b64, encoded_key, associated_data=None):
    """Decifra e devolve o objeto. Tag inválida levanta — nunca devolve lixo."""
    chave = load_key(encoded_key)
    nonce = base64.b64decode(nonce_b64)
    cifrado = base64.b64decode(ciphertext_b64)
    claro = AESGCM(chave).decrypt(nonce, cifrado, associated_data)
    return json.loads(claro.decode("utf-8"))
