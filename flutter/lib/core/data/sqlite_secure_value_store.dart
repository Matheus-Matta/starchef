import '../logging/app_logger.dart';
import '../storage/durable_secure_store.dart';
import 'payload_cipher.dart';
import 'pdv_database.dart';

/// Credenciais guardadas no **mesmo banco** que a operação do caixa.
///
/// O cofre do sistema continua sendo a primeira escolha. Esta camada existe
/// porque, em Ubuntu, ele falta com frequência — autostart sem sessão gráfica,
/// keyring bloqueado, empacotamento sem Secret Service — e a cópia em arquivo
/// ainda dependia de `chmod` funcionar no volume onde fica o `$HOME`. Quando
/// os dois falhavam, o operador perdia o login ao fechar o PDV e ficava sem
/// conseguir entrar no dia seguinte, com a internet fora.
///
/// O banco é o mesmo de pedidos, caixa e fila de impressão: se ele não abrir, o
/// PDV já avisa na inicialização e nada mais funciona offline de qualquer
/// forma. Guardar a sessão aqui alinha a durabilidade do login com a do resto.
///
/// **Sobre proteção**: o verificador de senha é PBKDF2 — guardá-lo em repouso é
/// seguro, é exatamente para isso que ele existe. Os tokens de sessão passam
/// pelo [PayloadCipher], que cifra quando há cofre disponível e degrada para
/// texto quando não há — a mesma exposição que a cópia em arquivo já tinha
/// nesse cenário, com a diferença de que agora o dado sobrevive.
class SqliteSecureValueStore implements SecureValueStore {
  SqliteSecureValueStore({required this.database, PayloadCipher? cipher})
    : _cipher = cipher ?? PayloadCipher.disabled();

  final PdvDatabase database;
  final PayloadCipher _cipher;

  @override
  Future<String?> read(String key) async {
    try {
      final row = await database.querySingle(
        'SELECT value FROM secure_values WHERE value_key = ?',
        [key],
      );
      if (row == null) return null;
      // `await` e não `return` direto: sem ele a falha de decifra acontece
      // FORA deste `try` e escapa como exceção, derrubando a abertura do PDV
      // em vez de valer como credencial ausente.
      return await _cipher.decrypt('${row['value']}');
    } catch (error) {
      // Um valor ilegível (a chave do cofre mudou entre reinstalações) equivale
      // a valor ausente: o operador entra de novo, em vez de o PDV travar.
      AppLogger.instance.warning(
        'credencial_local_ilegivel',
        data: {'chave': key, 'causa': '$error'},
      );
      return null;
    }
  }

  @override
  Future<void> write(String key, String value) async {
    final stored = await _cipher.encrypt(value);
    await database.execute(
      '''
      INSERT INTO secure_values(value_key, value, updated_at)
      VALUES (?, ?, ?)
      ON CONFLICT(value_key) DO UPDATE SET
        value = excluded.value,
        updated_at = excluded.updated_at
      ''',
      [key, stored, DateTime.now().toUtc().toIso8601String()],
    );
  }

  @override
  Future<void> delete(String key) async {
    await database.execute(
      'DELETE FROM secure_values WHERE value_key = ?',
      [key],
    );
  }
}
