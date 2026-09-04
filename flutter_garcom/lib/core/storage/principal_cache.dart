import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path_provider/path_provider.dart';

/// Uma resposta guardada, com o instante em que ela era verdade.
class CachedResponse {
  const CachedResponse({required this.payload, required this.updatedAt});

  final Map<String, dynamic> payload;
  final DateTime updatedAt;

  /// Há quanto tempo este dado foi confirmado pelo Caixa Principal.
  Duration get age => DateTime.now().difference(updatedAt);
}

/// Cópia local das últimas leituras confirmadas pelo Caixa Principal.
///
/// O aparelho do garçom não fala com a nuvem (§9) — ele lê pelo principal. Sem
/// esta cópia, o principal fora do ar significava tela vazia: nem a comanda
/// aberta há um minuto o garçom conseguia abrir. Com ela, o salão continua
/// trabalhando **até certo ponto**: dá para consultar o cardápio, as mesas, as
/// comandas e os pedidos que já tinham sido carregados, e lançar itens neles
/// (a escrita fica na fila do `RelayGateway`).
///
/// O que este cache **não** faz: fingir que o dado é atual. Toda resposta
/// servida daqui vem marcada com `_from_cache` e a idade, e a tela avisa. Um
/// pedido aberto em outro terminal depois da queda não aparece — e é
/// exatamente por isso que o aviso existe.
class PrincipalCache {
  PrincipalCache({this.testFile});

  /// Override para testes — evita tocar no diretório real do sistema.
  final File? testFile;

  /// Teto de entradas. O aparelho guarda o suficiente para um turno; guardar
  /// tudo transformaria o cache num banco sem manutenção.
  static const _maximumEntries = 120;

  /// Depois disso o dado é velho demais para orientar o salão sem um aviso
  /// forte. Ele continua sendo servido — melhor que uma tela vazia —, mas a
  /// interface trata como "pode ter mudado".
  static const staleAfter = Duration(minutes: 30);

  File? _file;
  Map<String, dynamic>? _entries;
  Future<void> _writeTail = Future.value();

  /// Chave estável para uma leitura: a rota mais os filtros, em ordem.
  static String keyFor(String path, Map<String, dynamic>? query) {
    final sorted = (query?.entries.toList() ?? [])
      ..sort((a, b) => a.key.compareTo(b.key));
    return '$path?${sorted.map((e) => '${e.key}=${e.value}').join('&')}';
  }

  Future<File> _resolveFile() async {
    final existing = _file;
    if (existing != null) return existing;
    final file =
        testFile ??
        await () async {
          final dir = await getApplicationSupportDirectory();
          return File(
            '${dir.path}${Platform.pathSeparator}garcom_principal_cache.json',
          );
        }();
    _file = file;
    return file;
  }

  Future<Map<String, dynamic>> _load() async {
    final cached = _entries;
    if (cached != null) return cached;
    try {
      final file = await _resolveFile();
      if (!await file.exists()) return _entries = {};
      final decoded = jsonDecode(await file.readAsString());
      return _entries = decoded is Map
          ? Map<String, dynamic>.from(decoded)
          : <String, dynamic>{};
    } catch (_) {
      // Arquivo corrompido ou de uma versão antiga: começar vazio é melhor do
      // que travar a abertura do app.
      return _entries = {};
    }
  }

  Future<CachedResponse?> read(String key) async {
    final entries = await _load();
    final row = entries[key];
    if (row is! Map) return null;
    final payload = row['payload'];
    final updatedAt = DateTime.tryParse('${row['updated_at'] ?? ''}');
    if (payload is! Map || updatedAt == null) return null;
    return CachedResponse(
      payload: Map<String, dynamic>.from(payload),
      updatedAt: updatedAt,
    );
  }

  /// Guarda a resposta.
  ///
  /// A memória é atualizada antes de devolver; o disco é gravado em segundo
  /// plano. Assim uma leitura logo depois de outra já encontra o valor, sem
  /// pagar a latência do arquivo em toda troca de tela.
  Future<void> write(String key, Map<String, dynamic> payload) async {
    final entries = await _load();
    entries[key] = {
      'payload': payload,
      'updated_at': DateTime.now().toIso8601String(),
    };
    if (entries.length > _maximumEntries) _evictOldest(entries);
    unawaited(_persist(Map<String, dynamic>.from(entries)));
  }

  /// Espera o arquivo alcançar a memória. Usado pelos testes e por quem
  /// precisa garantir a gravação antes de encerrar.
  Future<void> flush() => _writeTail;

  /// Idade da leitura mais recente guardada, para a tela avisar de quando são
  /// os dados que está mostrando.
  Future<DateTime?> newestUpdatedAt() async {
    final entries = await _load();
    DateTime? newest;
    for (final row in entries.values) {
      if (row is! Map) continue;
      final at = DateTime.tryParse('${row['updated_at'] ?? ''}');
      if (at == null) continue;
      if (newest == null || at.isAfter(newest)) newest = at;
    }
    return newest;
  }

  /// Esquece tudo. Chamado ao trocar de operador ou de Caixa Principal: o
  /// cache pertence a um pareamento, não ao aparelho.
  Future<void> clear() async {
    _entries = {};
    await _persist(const {});
  }

  static void _evictOldest(Map<String, dynamic> entries) {
    final ordered = entries.entries.toList()
      ..sort((a, b) {
        final left = '${(a.value as Map?)?['updated_at'] ?? ''}';
        final right = '${(b.value as Map?)?['updated_at'] ?? ''}';
        return left.compareTo(right);
      });
    for (final entry in ordered.take(entries.length - _maximumEntries)) {
      entries.remove(entry.key);
    }
  }

  /// Grava o arquivo inteiro, uma escrita de cada vez.
  Future<void> _persist(Map<String, dynamic> entries) {
    final future = _writeTail.then((_) => _write(entries));
    _writeTail = future.catchError((Object _) {});
    return future;
  }

  Future<void> _write(Map<String, dynamic> entries) async {
    try {
      final file = await _resolveFile();
      await file.parent.create(recursive: true);
      // Arquivo temporário e rename: uma queda de energia no meio da escrita
      // não pode deixar o cache pela metade e ilegível.
      final temp = File('${file.path}.tmp');
      await temp.writeAsString(jsonEncode(entries), flush: true);
      await temp.rename(file.path);
    } catch (_) {
      // Sem persistência o cache vale só para esta sessão; é degradação
      // aceitável, não motivo para impedir o garçom de trabalhar.
    }
  }
}
