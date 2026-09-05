import 'package:flutter/foundation.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/relay/pending_mutation.dart';
import '../data/orders_repository.dart';

/// O estado da lista de pedidos abertos, fora da árvore de widgets.
///
/// Mesma divisão do PDV desktop (`OrderPresenter`): a tela cuida de desenhar e
/// de navegar, e quem sabe carregar, de onde veio o dado e o que fazer com uma
/// falha é esta classe. Antes isso vivia no `State` da página, misturado com
/// `AppBar`, `ListView` e navegação — e não dava para exercitar nada disso sem
/// montar a tela inteira.
class OrdersPresenter extends ChangeNotifier {
  OrdersPresenter({required this.repository});

  final OrdersRepository repository;

  List<Map<String, dynamic>> _orders = const [];
  bool _loading = true;
  String? _error;
  ReadOrigin _origin = const ReadOrigin.live();
  bool _disposed = false;

  List<Map<String, dynamic>> get orders => _orders;
  bool get loading => _loading;
  String? get error => _error;

  /// De onde vieram os pedidos na tela: do Caixa Principal ou da cópia local.
  ReadOrigin get origin => _origin;

  Future<void> load() async {
    _loading = true;
    _error = null;
    _notify();
    try {
      final orders = await repository.openOrders();
      if (_disposed) return;
      _orders = orders;
      _origin = repository.lastReadOrigin;
    } catch (error) {
      if (_disposed) return;
      _error = describeFailure(error);
    } finally {
      _loading = false;
      _notify();
    }
  }

  /// Pedidos novos ainda não confirmados pelo caixa (fila offline) — sem
  /// isto, sair da tela de detalhe antes de sincronizar faria o pedido
  /// "sumir" até a rede voltar. `RelayGateway.pending` já sobrevive a fechar
  /// e abrir o app (`restore()` na inicialização), então não precisa de
  /// nenhum armazenamento novo aqui.
  List<Map<String, dynamic>> get creatingOrders => repository.gateway.pending
      .where((mutation) => mutation.kind == 'create_order')
      .map(_placeholderOrder)
      .toList();

  static Map<String, dynamic> _placeholderOrder(PendingMutation mutation) {
    final body = mutation.body ?? const <String, dynamic>{};
    final item = body['item'];
    return {
      'id': mutation.placeholderOrderId,
      '_offline_pending': true,
      'status': 'open',
      'order_type': body['order_type'],
      if (body['command'] != null) 'command': body['command'],
      if (body['table'] != null) 'table': body['table'],
      'items': item == null ? const [] : [item],
    };
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
