import 'package:flutter/foundation.dart';

import '../../../core/errors/failure_text.dart';
import '../data/orders_repository.dart';

/// O estado da tela inicial: TODAS as comandas, livres e em uso, 20 por vez.
///
/// O app serve só para lançar em comanda, então a tela inicial é a grade de
/// cartões — o garçom toca no número e já está no cardápio. Carregar tudo de
/// uma vez travaria a abertura em casa com centenas de cartões; carrega a
/// primeira página e busca o resto conforme ele rola.
class ComandasPresenter extends ChangeNotifier {
  ComandasPresenter({required this.repository, this.pageSize = 20});

  final OrdersRepository repository;
  final int pageSize;

  final _rows = <Map<String, dynamic>>[];
  int _nextPage = 1;
  bool _hasMore = true;
  bool _loading = false;
  String? _error;
  String _search = '';
  ReadOrigin _origin = const ReadOrigin.live();
  bool _disposed = false;

  /// Cada recomeço (busca nova, atualizar) ganha um número. Resposta de um
  /// recomeço anterior que chega atrasada é jogada fora — senão digitar "12"
  /// rápido podia terminar mostrando o resultado de "1".
  int _geracao = 0;

  List<Map<String, dynamic>> get rows => List.unmodifiable(_rows);
  bool get hasMore => _hasMore;
  bool get loading => _loading;
  String? get error => _error;
  String get search => _search;
  ReadOrigin get origin => _origin;

  Future<void> load() => _fetch(reset: true);

  /// A próxima página — chamada pela rolagem perto do fim.
  Future<void> loadMore() async {
    if (_loading || !_hasMore || _error != null) return;
    await _fetch(reset: false);
  }

  /// A página que falhou, de novo — sem perder o que já está na grade.
  Future<void> tentarDeNovo() {
    _error = null;
    return loadMore();
  }

  Future<void> buscar(String texto) {
    _search = texto.trim();
    return _fetch(reset: true);
  }

  Future<void> _fetch({required bool reset}) async {
    final geracao = reset ? ++_geracao : _geracao;
    final page = reset ? 1 : _nextPage;
    _loading = true;
    _error = null;
    _notify();
    try {
      final result = await repository.commands(
        page: page,
        search: _search,
        pageSize: pageSize,
        preview: true,
      );
      if (_disposed || geracao != _geracao) return;
      if (reset) _rows.clear();
      // Entre uma página e outra uma comanda pode mudar de lugar; repetida,
      // ela apareceria duas vezes na grade.
      final vistos = {for (final row in _rows) '${row['id']}'};
      _rows.addAll(result.rows.where((r) => vistos.add('${r['id']}')));
      _hasMore = result.hasMore;
      _nextPage = page + 1;
      _origin = repository.lastReadOrigin;
    } catch (error) {
      if (_disposed || geracao != _geracao) return;
      _error = describeFailure(error);
    } finally {
      if (!_disposed && geracao == _geracao) {
        _loading = false;
        _notify();
      }
    }
  }

  /// Relê SÓ a comanda que o garçom acabou de atender.
  ///
  /// Recarregar a grade inteira ao voltar jogava o garçom de volta ao topo,
  /// longe do cartão em que ele estava. Falhou (rede fora)? Fica o que estava:
  /// o contador de envios do topo já diz que algo está a caminho.
  Future<void> atualizar(String id) async {
    try {
      final response = await repository.commandItems(id);
      final command = response['command'];
      final index = _rows.indexWhere((row) => '${row['id']}' == id);
      if (_disposed || command is! Map || index < 0) return;
      _rows[index] = {..._rows[index], ...Map<String, dynamic>.from(command)};
      _notify();
    } catch (_) {
      return;
    }
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
