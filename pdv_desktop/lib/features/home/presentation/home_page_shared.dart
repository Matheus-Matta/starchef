// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O que TODA seção extraída da tela de vendas usa.
///
/// Existe por dois motivos concretos. O primeiro é evitar declarar o mesmo
/// membro em dois mixins: assinaturas iguais em lugares diferentes divergem
/// com o tempo, e o Dart recusa a classe quando isso acontece. O segundo é a
/// formatação — `_money` e `_number` eram `static` no `_HomePageState`, e um
/// membro estático não pode coexistir com um herdado de mesmo nome, então as
/// seções não conseguiriam chamá-los como antes.
///
/// Cada seção declara aqui EMBAIXO só o que é dela.
mixin _HomePageShared on State<HomePage> {
  double _number(dynamic value) => ValueFormatters.number(value);
  String _money(dynamic value) => ValueFormatters.money(value);

  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  ApiClient get api;
  bool get busy;
  set busy(bool value);
  String get token;
  String? get restaurantId;

  Future<List<Map<String, dynamic>>> _list(
    String path, {
    Map<String, dynamic>? query,
  });
  Future<T?> _work<T>(
    Future<T> Function() action, {
    String? errorTitle,
    void Function(Object error)? onError,
  });
  Future<bool> _printingStep(
    Future<void> Function() action, {
    required String title,
  });
  void _error(Object error, {String? title, String? action});

  /// O tradutor de códigos lidos, provido por `_ScanSection`. Está aqui
  /// porque a seção de ENTRADA também o usa, no painel que testa um código.
  CodeLookupService? get _codeLookup;

  // ── o rascunho, provido por `_DraftSection` ─────────────────────────────
  //
  // Estão AQUI, e não repetidos em cada seção, porque quatro delas consomem os
  // mesmos membros: lançamento por clique, por leitor, por configuração e por
  // pesagem. Quatro cópias da mesma assinatura divergem com o tempo, e o Dart
  // recusa a classe quando isso acontece — é o motivo de este mixin existir.
  bool get _draftIsLive;
  List<Map<String, dynamic>> get _cartItems;
  OrderDraftCart get draft;

  /// Quanto cada cartão anexado tem a cobrar, por id.
  ///
  /// Declarado aqui porque dois mixins o usam — o painel, para desenhar, e o
  /// fluxo, para mostrar o valor ao lado de cada comanda no diálogo. Nesta
  /// biblioteca cada seção é um mixin, e o analisador não liga as duas pontas
  /// sozinho.
  Map<String, double> get _totaisPorComanda;
  void _addLineToDraft(
    Map<String, dynamic> product, {
    double quantity,
    String? variationId,
    List<String> addonIds,
    String customerNote,
    double? weightKg,
    String? scaleReadingId,
  });
  void _changeDraftQuantity(String id, double quantity);
  void _removeDraftLine(String id);
  Future<void> _pickDraftType(String type);
  Future<void> _attachCommandToDraft();
  void _attachCommandToDraftDirectly(Map<String, dynamic> command);
  void _detachCommandFromDraft([String? commandId]);
  Future<bool> _materializeDraft();
  void _discardDraft();
  Future<bool> _confirmLeavingPendingItems();
}
