import '../../../core/network/api_exception.dart';
import '../../cash/domain/cash_restaurant_selector.dart';
import 'lista_da_estacao.dart';

/// Em qual restaurante a Balança Rápida abre.
///
/// A ordem: o que já estava escolhido nesta janela → o do caixa vinculado ao
/// usuário → o pedido por quem abriu a janela → o do cadastro do usuário → o
/// primeiro da lista. Um que não está mais disponível é pulado.
Future<String> restauranteDaEstacao({
  required ListaDaEstacao listas,
  required List<Map<String, dynamic>> restaurantes,
  required String userId,
  String? atual,
  String? pedido,
  String? doUsuario,
}) async {
  final disponiveis = restaurantes.map((item) => '${item['id']}').toSet();
  String? doCaixa;
  if (atual == null) {
    try {
      doCaixa = cashLinkedRestaurantId(
        cashStations: await listas.ler(
          '/cash-stations/',
          query: {'page_size': 300, 'is_active': true},
        ),
        userId: userId,
        availableRestaurantIds: disponiveis,
      );
    } on ApiException {
      // A balança continua usando a seleção anterior quando o vínculo do
      // caixa não pode ser consultado, inclusive no modo offline.
    }
  }
  final preferido = atual ?? doCaixa ?? pedido ?? doUsuario;
  return preferido != null && disponiveis.contains(preferido)
      ? preferido
      : '${restaurantes.first['id']}';
}
