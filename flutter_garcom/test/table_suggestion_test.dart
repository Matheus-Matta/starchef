import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/features/orders/presentation/order_dialogs.dart';

/// A mesa é o que liga a comanda ao salão. Entrar num pedido sem mesa e não
/// ser lembrado disso fazia a correção depender de o garçom lembrar sozinho,
/// no meio do atendimento — e a cozinha entregava sem saber para onde.
void main() {
  test('pedido de comanda sem mesa merece a sugestão', () {
    expect(
      shouldSuggestTable(const {'command': 'comanda-1', 'table': null}),
      isTrue,
    );
    expect(
      shouldSuggestTable(const {'command': 'comanda-1', 'table': ''}),
      isTrue,
    );
  });

  test('pedido que já tem mesa não é interrompido', () {
    expect(
      shouldSuggestTable(const {'command': 'comanda-1', 'table': 'mesa-3'}),
      isFalse,
    );
  });

  test('pedido sem comanda não tem mesa para vincular', () {
    // Balcão, entrega e retirada não passam pelo salão: sugerir mesa ali seria
    // oferecer algo que o backend nem aceita.
    expect(shouldSuggestTable(const {'order_type': 'counter'}), isFalse);
    expect(shouldSuggestTable(const {'command': '', 'table': ''}), isFalse);
  });

  test('sem pedido carregado não há o que sugerir', () {
    expect(shouldSuggestTable(null), isFalse);
  });
}
