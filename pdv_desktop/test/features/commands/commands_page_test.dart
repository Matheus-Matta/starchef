import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/api_client.dart';
import 'package:starchef_pdv_desktop/core/network/api_exception.dart';
import 'package:starchef_pdv_desktop/features/commands/data/command_repository.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/commands_page.dart';

/// Um repositório que falha do jeito que se pediu.
///
/// Herda de [CommandRepository] em vez de implementar uma interface porque o
/// que está sob teste é o TRATAMENTO da falha na tela, não o contrato do
/// repositório.
class _RepositorioQueFalha extends CommandRepository {
  _RepositorioQueFalha(this.erro) : super(ApiClient(baseUrl: 'http://x'));

  final Object erro;

  @override
  Future<List<Map<String, dynamic>>> list({String? restaurantId}) async {
    throw erro;
  }
}

class _RepositorioVazio extends CommandRepository {
  _RepositorioVazio() : super(ApiClient(baseUrl: 'http://x'));

  @override
  Future<List<Map<String, dynamic>>> list({String? restaurantId}) async =>
      const [];
}

Widget _tela(CommandRepository repositorio) => MaterialApp(
  home: Scaffold(
    body: CommandsPage(
      repository: repositorio,
      // A tela agora é o desenho da venda: catálogo no meio, carrinho à
      // direita. Sem produto nenhum ela ainda precisa carregar e mostrar o
      // recado de falha — que é o que estes testes provam.
      products: const [],
      categories: const [],
    ),
  ),
);

void main() {
  /// A resolução REAL de um posto de venda.
  ///
  /// O canvas padrão do teste é 800×600, que não existe em nenhum balcão —
  /// medir a tela nele reprovaria um layout que funciona e aprovaria um que
  /// não cabe no monitor de verdade.
  group('a pagina de comandas sempre sai do carregando', () {
    testWidgets('falha da API vira recado, nao tela parada', (tester) async {
      await _montar(
        tester,
        _tela(_RepositorioQueFalha(const ApiException('Servidor indisponível'))),
      );

      expect(find.textContaining('Servidor indisponível'), findsOneWidget);
      expect(find.text('Carregando…'), findsNothing);
    });

    testWidgets('falha que NAO e ApiException tambem vira recado', (
      tester,
    ) async {
      // Este é o caso que deixava a tela girando em silêncio: só
      // `on ApiException` era capturado, e um `TypeError` de conversão ou uma
      // exceção crua da rede escapavam sem deixar recado nenhum. O operador
      // via uma página parada, sem saber se ainda estava vindo.
      await _montar(
        tester,
        _tela(_RepositorioQueFalha(StateError('conexão encerrada'))),
      );

      expect(find.textContaining('Falha ao carregar'), findsOneWidget);
      expect(find.text('Carregando…'), findsNothing);
    });

    testWidgets('lista vazia diz que esta vazia, e nao que esta carregando', (
      tester,
    ) async {
      await _montar(tester, _tela(_RepositorioVazio()));

      expect(find.text('Nenhuma comanda encontrada.'), findsOneWidget);
      expect(find.text('Carregando…'), findsNothing);
      // Sem cartão escolhido, o carrinho convida a escolher um — e não mostra
      // o consumo de ninguém.
      expect(find.textContaining('Passe o cartão'), findsWidgets);
    });
  });

  group('o salao vem antes do cartao aberto', () {
    testWidgets('a tela abre na GRADE, sem catalogo e sem carrinho', (
      tester,
    ) async {
      // A ordem é a do gesto: primeiro o cliente, depois o que ele pediu.
      // Abrir direto no catálogo obrigava a escolher a comanda numa coluna
      // estreita ao lado dos produtos.
      await _montar(tester, _tela(_RepositorioComComanda()));

      expect(find.text('13'), findsOneWidget);
      expect(find.text('Total pendente'), findsNothing);
      expect(find.text('Enviar à cozinha'), findsNothing);
    });

    testWidgets('tocar no cartao abre o detalhe com o carrinho', (
      tester,
    ) async {
      await _montar(tester, _tela(_RepositorioComComanda()));

      await tester.tap(find.text('13'));
      await tester.pumpAndSettle();

      expect(find.text('Comanda 13'), findsOneWidget);
      expect(find.text('Total pendente'), findsOneWidget);
      expect(find.text('Enviar à cozinha'), findsOneWidget);
      // Não existe pagamento aqui: cobrar é gesto do caixa, no pedido.
      expect(find.textContaining('Pagamento'), findsNothing);
    });

    testWidgets('dá para voltar ao salao', (tester) async {
      await _montar(tester, _tela(_RepositorioComComanda()));
      await tester.tap(find.text('13'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('Todas as comandas'));
      await tester.pumpAndSettle();

      expect(find.text('Total pendente'), findsNothing);
      expect(find.text('13'), findsOneWidget);
    });
  });
}

/// Um repositório com uma comanda ocupada e um item pendente nela.
class _RepositorioComComanda extends CommandRepository {
  _RepositorioComComanda() : super(ApiClient(baseUrl: 'http://x'));

  @override
  Future<List<Map<String, dynamic>>> list({String? restaurantId}) async => [
    {
      'id': 'c13',
      'number': 13,
      'code': 'CMD-0013',
      'pending_items': 1,
      'pending_total': '42.00',
    },
  ];

  @override
  Future<Map<String, dynamic>> items(String commandId, {bool history = false}) async => {
    'items': [
      {
        'id': 'i1',
        'product_name': 'Picanha',
        'quantity': 1,
        'total_price': '42.00',
        'status': 'pending',
      },
    ],
  };
}

/// Monta a tela na resolução de um posto de venda de verdade.
Future<void> _montar(WidgetTester tester, Widget tela) async {
  tester.view.physicalSize = const Size(1366, 768);
  tester.view.devicePixelRatio = 1;
  addTearDown(() {
    tester.view.resetPhysicalSize();
    tester.view.resetDevicePixelRatio();
  });
  await tester.pumpWidget(tela);
  await tester.pumpAndSettle();
}
