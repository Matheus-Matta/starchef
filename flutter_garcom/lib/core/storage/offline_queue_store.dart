import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

import '../relay/pending_mutation.dart';

/// Persiste a fila de operações offline em um arquivo JSON no diretório de
/// dados do app.
///
/// Precisa sobreviver a fechar e abrir o app: um item lançado sem rede não
/// pode desaparecer se o garçom trocar de tela ou o celular reiniciar antes da
/// conexão voltar.
class OfflineQueueStore {
  OfflineQueueStore({this.testFile});

  /// Override para testes — evita tocar no diretório real do sistema.
  final File? testFile;
  File? _file;
  Future<void> _writeTail = Future.value();

  Future<File> _resolveFile() async {
    final existing = _file;
    if (existing != null) return existing;
    final file =
        testFile ??
        await () async {
          final dir = await getApplicationSupportDirectory();
          return File(
            '${dir.path}${Platform.pathSeparator}garcom_outbox.json',
          );
        }();
    _file = file;
    return file;
  }

  /// Arquivo das recusas, ao lado da fila.
  ///
  /// Uma recusa é um item que o garçom lançou e o Caixa Principal não aceitou
  /// — ela precisa sobreviver a fechar o app tanto quanto a fila: enquanto
  /// vivia só em memória, o item sumia da tela no primeiro reinício e ninguém
  /// mais sabia que ele existiu.
  File? _failedFile;

  Future<File> _resolveFailedFile() async {
    final existing = _failedFile;
    if (existing != null) return existing;
    final queue = await _resolveFile();
    final file = File(
      '${queue.path.replaceFirst(RegExp(r'\.json$'), '')}_recusadas.json',
    );
    _failedFile = file;
    return file;
  }

  Future<List<FailedMutation>> loadFailed() async {
    try {
      final file = await _resolveFailedFile();
      if (!await file.exists()) return [];
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) return [];
      final decoded = jsonDecode(raw);
      if (decoded is! List) return [];
      return decoded
          .whereType<Map>()
          .map((row) => FailedMutation.fromJson(Map<String, dynamic>.from(row)))
          .toList();
    } catch (_) {
      return [];
    }
  }

  Future<void> saveFailed(List<FailedMutation> failures) {
    final future = _writeTail.then((_) async {
      final file = await _resolveFailedFile();
      await file.writeAsString(
        jsonEncode(failures.map((item) => item.toJson()).toList()),
        flush: true,
      );
    });
    _writeTail = future.catchError((_) {});
    return future;
  }

  Future<List<PendingMutation>> load() async {
    try {
      final file = await _resolveFile();
      if (!await file.exists()) return [];
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) return [];
      final decoded = jsonDecode(raw);
      if (decoded is! List) return [];
      return decoded
          .whereType<Map>()
          .map((row) => PendingMutation.fromJson(Map<String, dynamic>.from(row)))
          .toList();
    } catch (_) {
      // Arquivo corrompido ou de uma versão antiga: melhor começar vazio do
      // que travar o app na inicialização.
      return [];
    }
  }

  /// Grava a fila inteira. As chamadas são encadeadas (uma de cada vez) para
  /// duas gravações concorrentes não se sobreporem e corromperem o arquivo.
  Future<void> save(List<PendingMutation> mutations) {
    final future = _writeTail.then((_) => _write(mutations));
    _writeTail = future.catchError((_) {});
    return future;
  }

  Future<void> _write(List<PendingMutation> mutations) async {
    try {
      final file = await _resolveFile();
      await file.parent.create(recursive: true);
      final encoded = jsonEncode(mutations.map((m) => m.toJson()).toList());
      // Escreve em um arquivo temporário e renomeia: uma queda de energia no
      // meio da escrita não pode deixar o arquivo pela metade e ilegível.
      final temp = File('${file.path}.tmp');
      await temp.writeAsString(encoded, flush: true);
      await temp.rename(file.path);
    } catch (_) {
      // Sem persistência a fila continua funcionando em memória nesta sessão;
      // só não sobrevive a fechar o app.
    }
  }
}
