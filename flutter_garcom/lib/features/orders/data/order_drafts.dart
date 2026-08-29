import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../../../core/relay/relay_signature.dart';

/// Um item escolhido pelo garçom que ainda **não** foi mandado a lugar nenhum.
///
/// O lançamento deixou de sair do aparelho item a item: cada toque virava uma
/// ida à rede que podia falhar sozinha, e o garçom só descobria o problema
/// muito depois, numa pendência que não dizia mais de que item se tratava.
/// Agora os itens se acumulam aqui e vão juntos, num envio só, quando ele
/// confirma — que é também quando a comanda é impressa.
class DraftItem {
  const DraftItem({
    required this.id,
    required this.orderId,
    required this.productId,
    required this.productName,
    required this.quantity,
    required this.addonIds,
    required this.note,
    this.variationId,
    this.variationName,
  });

  /// Identificador local, só para remover a linha certa da lista.
  final String id;
  final String orderId;
  final String productId;
  final String productName;
  final int quantity;
  final String? variationId;
  final String? variationName;
  final List<String> addonIds;
  final String note;

  String get label => variationName == null || variationName!.isEmpty
      ? '${quantity}x $productName'
      : '${quantity}x $productName - $variationName';

  Map<String, dynamic> toJson() => {
    'id': id,
    'order_id': orderId,
    'product_id': productId,
    'product_name': productName,
    'quantity': quantity,
    'variation_id': variationId,
    'variation_name': variationName,
    'addon_ids': addonIds,
    'note': note,
  };

  static DraftItem fromJson(Map<String, dynamic> json) => DraftItem(
    id: '${json['id'] ?? ''}',
    orderId: '${json['order_id'] ?? ''}',
    productId: '${json['product_id'] ?? ''}',
    productName: '${json['product_name'] ?? ''}',
    quantity: (json['quantity'] as num?)?.toInt() ?? 1,
    variationId: json['variation_id'] as String?,
    variationName: json['variation_name'] as String?,
    addonIds: (json['addon_ids'] as List? ?? const [])
        .map((value) => '$value')
        .toList(),
    note: '${json['note'] ?? ''}',
  );
}

/// Os itens escolhidos e ainda não enviados, por pedido.
///
/// Grava em disco a cada mudança pelo mesmo motivo da fila offline: o celular
/// do garçom fecha, cai e reinicia no meio do salão, e um item escolhido não
/// pode depender de a tela continuar aberta para existir.
class OrderDrafts extends ChangeNotifier {
  OrderDrafts({this.testFile});

  /// Override para testes — evita tocar no diretório real do sistema.
  final File? testFile;
  final List<DraftItem> _items = [];
  File? _file;
  Future<void> _writeTail = Future.value();
  bool _restored = false;

  List<DraftItem> forOrder(String orderId) =>
      _items.where((item) => item.orderId == orderId).toList();

  int countFor(String orderId) => forOrder(orderId).length;

  bool get isEmpty => _items.isEmpty;

  Future<void> restore() async {
    if (_restored) return;
    _restored = true;
    _items.addAll(await _load());
    if (_items.isNotEmpty) notifyListeners();
  }

  Future<DraftItem> add(DraftItem item) async {
    _items.add(item);
    notifyListeners();
    await _persist();
    return item;
  }

  Future<void> remove(String id) async {
    _items.removeWhere((item) => item.id == id);
    notifyListeners();
    await _persist();
  }

  /// Os itens deste pedido saíram: a lista dele zera.
  Future<void> clearOrder(String orderId) async {
    _items.removeWhere((item) => item.orderId == orderId);
    notifyListeners();
    await _persist();
  }

  /// Um pedido criado offline recebeu o id real: os rascunhos acompanham.
  Future<void> reassign(String fromOrderId, String toOrderId) async {
    var changed = false;
    for (var index = 0; index < _items.length; index++) {
      final item = _items[index];
      if (item.orderId != fromOrderId) continue;
      _items[index] = DraftItem(
        id: item.id,
        orderId: toOrderId,
        productId: item.productId,
        productName: item.productName,
        quantity: item.quantity,
        variationId: item.variationId,
        variationName: item.variationName,
        addonIds: item.addonIds,
        note: item.note,
      );
      changed = true;
    }
    if (!changed) return;
    notifyListeners();
    await _persist();
  }

  static String newId() => RelaySignature.randomId();

  Future<File> _resolveFile() async {
    final existing = _file;
    if (existing != null) return existing;
    final file =
        testFile ??
        await () async {
          final dir = await getApplicationSupportDirectory();
          return File(
            '${dir.path}${Platform.pathSeparator}garcom_itens_rascunho.json',
          );
        }();
    _file = file;
    return file;
  }

  Future<List<DraftItem>> _load() async {
    try {
      final file = await _resolveFile();
      if (!await file.exists()) return [];
      final raw = await file.readAsString();
      if (raw.trim().isEmpty) return [];
      final decoded = jsonDecode(raw);
      if (decoded is! List) return [];
      return decoded
          .whereType<Map>()
          .map((row) => DraftItem.fromJson(Map<String, dynamic>.from(row)))
          .toList();
    } catch (_) {
      // Arquivo corrompido ou de versão anterior: melhor começar vazio do que
      // travar o app na abertura.
      return [];
    }
  }

  /// Gravações encadeadas: dois toques seguidos não podem se sobrepor e
  /// corromper o arquivo.
  Future<void> _persist() {
    final future = _writeTail.then((_) async {
      final file = await _resolveFile();
      await file.writeAsString(
        jsonEncode(_items.map((item) => item.toJson()).toList()),
        flush: true,
      );
    });
    _writeTail = future.catchError((_) {});
    return future;
  }
}
