import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import '../logging/app_logger.dart';
import '../storage/durable_secure_store.dart';

/// Proteção em repouso dos payloads sigilosos do banco local (§15).
///
/// A configuração da NFC-e guarda CSC, ID CSC e ambiente de emissão; o
/// cadastro de usuários guarda hash de senha e vínculos. Esses registros
/// precisam existir offline — sem eles não há venda com nota nem login sem
/// rede —, mas gravá-los em texto puro deixaria a credencial fiscal do
/// estabelecimento legível para qualquer processo que abrisse o arquivo.
///
/// A construção é HMAC-SHA256 em modo contador (keystream) seguida de um
/// HMAC-SHA256 sobre o criptograma — encrypt-then-MAC. É o que dá para fazer
/// com as dependências já presentes no projeto (`crypto`), e cobre o risco
/// real aqui: leitura do arquivo por outro processo ou cópia do backup. Não
/// substitui criptografia de disco quando a máquina toda estiver em risco.
///
/// A chave-mestra vive no armazenamento seguro do sistema
/// ([SecureValueStore]), o mesmo usado pela sessão e pelo pareamento — assim
/// copiar apenas o `.sqlite` não basta para ler nada.
class PayloadCipher {
  PayloadCipher({required SecureValueStore store}) : _store = store;

  /// Cifrador inerte, para testes e para instalações que optem por não
  /// proteger o payload. Devolve e aceita texto puro.
  PayloadCipher.disabled() : _store = null;

  static const _keyName = 'starchef.local.payload.key.v1';
  static const _prefix = 'enc:v1:';

  final SecureValueStore? _store;
  Uint8List? _key;
  Future<Uint8List?>? _loading;
  bool _degraded = false;

  /// `false` no cifrador inerte: o chamador grava texto puro.
  bool get enabled => _store != null && !_degraded;

  /// O cofre do sistema não respondeu e a proteção foi desligada.
  ///
  /// Acontece em instalações Linux sem Secret Service (autostart sem GNOME
  /// Keyring/KWallet) e em perfis Windows onde o DPAPI do usuário falha.
  bool get degraded => _degraded;

  Future<Uint8List?> _masterKey() {
    final cached = _key;
    if (cached != null) return Future.value(cached);
    return _loading ??= _loadOrCreateKey();
  }

  Future<Uint8List?> _loadOrCreateKey() async {
    final store = _store;
    if (store == null) return null;
    try {
      final stored = await store.read(_keyName);
      if (stored != null && stored.isNotEmpty) {
        _key = Uint8List.fromList(base64Decode(stored));
        return _key;
      }
      final random = Random.secure();
      final fresh = Uint8List.fromList(
        List<int>.generate(32, (_) => random.nextInt(256)),
      );
      await store.write(_keyName, base64Encode(fresh));
      _key = fresh;
      return fresh;
    } catch (error) {
      // Sem cofre não há como guardar a chave — e cifrar com uma chave que se
      // perde no próximo boot é pior do que não cifrar: a configuração fiscal
      // ficaria ilegível e o terminal não emitiria nota nenhuma offline.
      // Degrada para texto puro e registra, para que a instalação seja
      // corrigida (no Ubuntu: `libsecret-1-0` e um keyring desbloqueado).
      _degraded = true;
      AppLogger.instance.error(
        'cofre_indisponivel_payload_sem_cifra',
        data: {'plataforma': Platform.operatingSystem},
        cause: error,
      );
      return null;
    }
  }

  /// Já está cifrado? Serve para migrar bases antigas sem reescrever tudo.
  static bool isCiphertext(String value) => value.startsWith(_prefix);

  Future<String> encrypt(String plaintext) async {
    if (!enabled) return plaintext;
    final key = await _masterKey();
    if (key == null) return plaintext;
    final random = Random.secure();
    final nonce = Uint8List.fromList(
      List<int>.generate(16, (_) => random.nextInt(256)),
    );
    final data = Uint8List.fromList(utf8.encode(plaintext));
    final cipherText = _xorKeystream(key, nonce, data);
    final tag = Hmac(
      sha256,
      _subkey(key, 'mac'),
    ).convert([...nonce, ...cipherText]).bytes;
    return '$_prefix${base64Encode(nonce)}:${base64Encode(cipherText)}'
        ':${base64Encode(tag)}';
  }

  /// Decifra; devolve o próprio valor quando ele nunca foi cifrado.
  ///
  /// Lança [FormatException] se a autenticação falhar: um payload fiscal
  /// adulterado não pode virar dado operacional em silêncio.
  Future<String> decrypt(String value) async {
    if (!isCiphertext(value)) return value;
    final parts = value.substring(_prefix.length).split(':');
    if (parts.length != 3) {
      throw const FormatException('Payload local cifrado em formato inválido.');
    }
    final key = await _masterKey();
    if (key == null) {
      throw const FormatException(
        'Payload local cifrado sem chave disponível no cofre do sistema.',
      );
    }
    final Uint8List nonce;
    final Uint8List cipherText;
    final List<int> tag;
    try {
      nonce = Uint8List.fromList(base64Decode(parts[0]));
      cipherText = Uint8List.fromList(base64Decode(parts[1]));
      tag = base64Decode(parts[2]);
    } on FormatException catch (error) {
      // Um erro de base64 cru ("Invalid length, must be multiple of four")
      // não diz nada a quem lê o log. O que importa é que o registro está
      // ilegível e precisa vir de novo da sincronização.
      throw FormatException(
        'Payload local cifrado está corrompido: ${error.message}',
      );
    }
    final expected = Hmac(
      sha256,
      _subkey(key, 'mac'),
    ).convert([...nonce, ...cipherText]).bytes;
    if (!_constantTimeEquals(tag, expected)) {
      throw const FormatException(
        'Payload local cifrado não pôde ser autenticado.',
      );
    }
    return utf8.decode(_xorKeystream(key, nonce, cipherText));
  }

  static Uint8List _subkey(Uint8List key, String label) => Uint8List.fromList(
    Hmac(sha256, key).convert(utf8.encode('starchef:$label')).bytes,
  );

  static Uint8List _xorKeystream(
    Uint8List key,
    Uint8List nonce,
    Uint8List data,
  ) {
    final streamKey = _subkey(key, 'stream');
    final output = Uint8List(data.length);
    var counter = 0;
    var offset = 0;
    while (offset < data.length) {
      final block = Hmac(sha256, streamKey).convert([
        ...nonce,
        (counter >> 24) & 0xff,
        (counter >> 16) & 0xff,
        (counter >> 8) & 0xff,
        counter & 0xff,
      ]).bytes;
      for (var i = 0; i < block.length && offset < data.length; i++, offset++) {
        output[offset] = data[offset] ^ block[i];
      }
      counter++;
    }
    return output;
  }

  static bool _constantTimeEquals(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    var diff = 0;
    for (var i = 0; i < a.length; i++) {
      diff |= a[i] ^ b[i];
    }
    return diff == 0;
  }
}
