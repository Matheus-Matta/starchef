import 'dart:async';

/// Avisos de que um conjunto de dados mudou localmente.
///
/// O PDV nunca espera a rede para desenhar: ele lê do armazenamento local e
/// segue. Quando uma resposta nova chega — ou quando uma alteração offline é
/// gravada —, o assunto correspondente é sinalizado e as telas interessadas
/// releem. É isso que dá o efeito de tempo real sem que nenhuma tela fique
/// presa em um timeout de requisição.
///
/// Os assuntos são grosseiros de propósito. Sinalizar "pedidos mudaram" custa
/// uma releitura local barata; rastrear a mudança até o campo exigiria um
/// modelo de eventos que este PDV não tem, e erraria mais do que acertaria.
class DataSignals {
  final _controller = StreamController<String>.broadcast();
  final _pending = <String>{};
  Timer? _debounce;
  bool _closed = false;

  /// Agrupa avisos próximos: uma sincronização que atualiza vinte pedidos
  /// deve provocar uma releitura, não vinte.
  static const _window = Duration(milliseconds: 120);

  Stream<String> get changes => _controller.stream;

  /// Fluxo de um assunto específico.
  Stream<void> on(String topic) =>
      changes.where((value) => value == topic);

  void emit(String topic) {
    if (_closed || topic.isEmpty) return;
    _pending.add(topic);
    _debounce?.cancel();
    _debounce = Timer(_window, _flush);
  }

  /// Deriva o assunto a partir da rota da API.
  ///
  /// `null` para rotas que nenhuma tela observa — não vale acordar ninguém
  /// por um trabalho de impressão ou uma leitura de balança.
  static String? topicFor(String path) {
    if (path.startsWith('/orders/')) return 'orders';
    if (path.startsWith('/customers/')) return 'customers';
    if (path.startsWith('/menu/')) return 'menu';
    if (path.startsWith('/tables/')) return 'tables';
    if (path.startsWith('/cash-register/')) return 'cash';
    if (path.startsWith('/payments/')) return 'payments';
    return null;
  }

  void _flush() {
    if (_closed) return;
    final topics = _pending.toList(growable: false);
    _pending.clear();
    for (final topic in topics) {
      if (!_controller.isClosed) _controller.add(topic);
    }
  }

  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    _debounce?.cancel();
    _pending.clear();
    await _controller.close();
  }
}
