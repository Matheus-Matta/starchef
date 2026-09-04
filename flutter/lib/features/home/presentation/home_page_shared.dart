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
  // `action` é usado pela própria tela (`_error(..., action: ...)`); o
  // analisador não enxerga isso a partir da declaração abstrata.
  // ignore: unused_element_parameter
  void _error(Object error, {String? title, String? action});
}
