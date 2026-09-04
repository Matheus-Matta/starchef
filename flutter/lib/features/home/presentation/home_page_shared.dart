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
}
