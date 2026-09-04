import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/local_id.dart';
import 'package:starchef_pdv/core/data/payload_cipher.dart';
import 'package:starchef_pdv/core/storage/durable_secure_store.dart';

/// Armazenamento em memória, no lugar do cofre do sistema operacional.
class _MemoryStore implements SecureValueStore {
  final Map<String, String> values = {};

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;

  @override
  Future<void> delete(String key) async => values.remove(key);
}

/// A configuração fiscal guarda CSC e ID CSC — a credencial que autoriza a
/// loja a emitir NFC-e. Ela precisa existir offline (§15) e não pode ficar
/// legível para quem abrir o arquivo do banco ou copiar um backup.
void main() {
  test('cifra e decifra o mesmo texto, com a chave guardada no cofre', () async {
    final store = _MemoryStore();
    final cipher = PayloadCipher(store: store);
    const segredo = '{"csc":"ABC123","id_csc":"000001","ambiente":"producao"}';

    final cifrado = await cipher.encrypt(segredo);

    expect(cifrado, isNot(contains('ABC123')));
    expect(PayloadCipher.isCiphertext(cifrado), isTrue);
    expect(await cipher.decrypt(cifrado), segredo);
    expect(store.values, isNotEmpty);
  });

  test('duas cifras do mesmo texto são diferentes', () async {
    final cipher = PayloadCipher(store: _MemoryStore());

    final a = await cipher.encrypt('mesmo conteudo');
    final b = await cipher.encrypt('mesmo conteudo');

    // Nonce por gravação: sem isso dava para dizer que dois registros têm o
    // mesmo valor só comparando os bytes no disco.
    expect(a, isNot(b));
    expect(await cipher.decrypt(a), await cipher.decrypt(b));
  });

  test('payload adulterado é recusado em vez de virar dado operacional', () async {
    final cipher = PayloadCipher(store: _MemoryStore());
    final cifrado = await cipher.encrypt('{"csc":"ABC123"}');
    final partes = cifrado.split(':');
    // Troca um byte do criptograma mantendo o formato.
    final adulterado = [
      partes[0],
      partes[1],
      partes[2],
      'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
      partes[4],
    ].join(':');

    await expectLater(
      cipher.decrypt(adulterado),
      throwsA(isA<FormatException>()),
    );
  });

  test('texto que nunca foi cifrado passa direto', () async {
    // Permite abrir uma base gravada antes desta versão sem migração.
    final cipher = PayloadCipher(store: _MemoryStore());

    expect(await cipher.decrypt('{"name":"Coxinha"}'), '{"name":"Coxinha"}');
  });

  test('o cifrador inerte devolve o texto puro', () async {
    final cipher = PayloadCipher.disabled();

    expect(cipher.enabled, isFalse);
    expect(await cipher.encrypt('texto'), 'texto');
    expect(await cipher.decrypt('texto'), 'texto');
  });

  test('identificador local é um UUID v4 e nunca se repete (§7)', () {
    final gerados = {for (var i = 0; i < 500; i++) LocalId.uuid()};

    expect(gerados, hasLength(500));
    expect(
      gerados.first,
      matches(
        RegExp(
          r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
        ),
      ),
    );
  });

  test('identificador temporário é reconhecível', () {
    final temporario = LocalId.temporary();

    expect(LocalId.isTemporary(temporario), isTrue);
    expect(LocalId.isTemporary('pedido-real'), isFalse);
    expect(LocalId.isTemporary(null), isFalse);
  });
}
