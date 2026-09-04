import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';

import 'pdv_test_support.dart';

/// **O mapa de rotas do PDV, fixado.**
///
/// Cada linha aqui é uma chamada que o aplicativo realmente faz. O erro que
/// este arquivo existe para impedir não aparece como exceção: aparece como uma
/// operação silenciosamente aplicada no recurso errado. Foi assim que
/// `DELETE /orders/<id>/payments/<id>/` — um estorno — chegou a marcar o
/// **pedido inteiro** como excluído, porque caiu no caminho genérico de
/// escrita.
///
/// Ao acrescentar uma rota no aplicativo, acrescente-a aqui e diga o que ela é.
void main() {
  late TestPdvStack stack;

  setUp(() async {
    stack = await TestPdvStack.create();
    // Estado normal de operação: sessão vinculada e servidor respondendo.
    stack.gateway.connectivity = () => true;
  });

  tearDown(() async => stack.dispose());

  /// Rotas atendidas pelo SQLite: leitura imediata e escrita enfileirada.
  const locais = <String, String>{
    '/menu/products/': 'catálogo',
    '/menu/categories/': 'catálogo',
    '/menu/addons/': 'catálogo',
    '/menu/variations/': 'catálogo',
    '/restaurants/': 'estabelecimento',
    '/tables/': 'salão',
    '/tables/sectors/': 'salão',
    '/commands/': 'salão',
    '/customers/': 'clientes',
    '/payments/methods/': 'recebimento',
    '/cash-stations/': 'caixa',
    '/printers/': 'periféricos',
    '/scales/': 'periféricos',
    '/orders/': 'operação',
  };

  /// Rotas que só o servidor sabe responder.
  const servidor = <String, String>{
    '/auth/login/': 'autenticação',
    '/auth/refresh/': 'autenticação',
    '/auth/logout/': 'autenticação',
    '/restaurants/rest-1/cash-auth/': 'senha de ações do caixa',
    '/print-jobs/': 'fila de trabalhos do backend',
    '/print-jobs/job-1/mark-printed/': 'confirmação de impressão',
    '/print-jobs/job-1/mark-failed/': 'confirmação de impressão',
    '/print-jobs/job-1/requeue/': 'reenfileirar no backend',
    '/printers/templates/': 'modelos (não é coleção de entidades)',
    '/printers/imp-1/test-connection/': 'diagnóstico do equipamento',
    '/scales/readings/': 'leitura física, criada no instante da pesagem',
    '/scales/bal-1/latest-reading/': 'leitura física',
    '/orders/pedido-1/print/': 'renderização do cupom pelo backend',
    '/invoices/nota-1/print/': 'DANFE não existe sem nota autorizada',
    '/reports/sales/': 'relatório não é operação de balcão',
  };

  test('as rotas de operação são atendidas pelo banco local', () {
    for (final entry in locais.entries) {
      expect(
        stack.gateway.handlesRead(entry.key),
        isTrue,
        reason: '${entry.key} (${entry.value}) precisa abrir sem internet',
      );
      expect(
        stack.gateway.handlesWrite('POST', entry.key, const {}),
        isTrue,
        reason: '${entry.key} (${entry.value})',
      );
    }
  });

  test('as rotas que exigem servidor nunca são atendidas localmente', () {
    for (final entry in servidor.entries) {
      expect(
        stack.gateway.handlesRead(entry.key),
        isFalse,
        reason: '${entry.key}: ${entry.value}',
      );
      expect(
        stack.gateway.handlesWrite('POST', entry.key, const {}),
        isFalse,
        reason: '${entry.key}: ${entry.value}',
      );
    }
  });

  test('cada ação do atendimento é aplicada onde deve', () {
    // O pedido tem ações próprias; qualquer outra precisa do servidor, porque
    // aplicá-la genericamente alteraria o próprio pedido.
    const doPedido = [
      '/orders/pedido-1/items/',
      '/orders/pedido-1/items/item-1/void/',
      '/orders/pedido-1/close/',
      '/orders/pedido-1/pay/',
      '/orders/pedido-1/send-to-kitchen/',
    ];
    for (final path in doPedido) {
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isTrue,
        reason: path,
      );
    }

    const naoDoPedido = [
      // Estorno: já marcou o pedido inteiro como excluído.
      '/orders/pedido-1/payments/pagamento-1/',
      '/orders/pedido-1/print/',
      '/orders/pedido-1/comp/',
    ];
    for (final path in naoDoPedido) {
      expect(
        stack.gateway.handlesWrite('DELETE', path, const {}),
        isFalse,
        reason: path,
      );
    }
  });

  test('o turno de caixa é local; a aprovação prefere o servidor', () {
    for (final path in const [
      '/cash-register/open/',
      '/cash-register/sessao-1/close/',
      '/cash-register/sessao-1/withdrawal/',
      '/cash-register/sessao-1/supply/',
    ]) {
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isTrue,
        reason: path,
      );
    }
    expect(stack.gateway.handlesRead('/cash-register/current/'), isTrue);

    // Online a aprovação também aceita login de gerente, que só o servidor
    // valida. Offline ela é aplicada aqui, com a prova da senha do caixa.
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/cash-register/sessao-1/approve/',
        const {},
      ),
      isFalse,
    );
    stack.gateway.connectivity = () => false;
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/cash-register/sessao-1/approve/',
        const {},
      ),
      isTrue,
    );
  });

  test('rotas parecidas não se confundem', () {
    // Prefixos que já resolveram para o recurso errado.
    expect(
      EntityCatalog.resolve('/tables/sectors/')!.type,
      EntityCatalog.tableSector,
    );
    expect(
      EntityCatalog.resolve('/customers/addresses/')!.type,
      EntityCatalog.customerAddress,
    );
    expect(
      EntityCatalog.resolve('/payments/methods/')!.type,
      EntityCatalog.paymentMethod,
    );
    // `/printers/templates/` resolveria como uma impressora de id "templates".
    // Por isso ele é barrado antes, na lista de rotas de servidor.
    expect(stack.gateway.handlesRead('/printers/templates/'), isFalse);
  });

  test('num caixa secundário, só passa o que o principal sabe executar', () {
    stack.gateway.relayOnly = true;

    expect(stack.gateway.handlesWrite('POST', '/orders/', const {}), isTrue);
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/orders/pedido-real-12345678/close/',
        const {},
      ),
      isTrue,
    );
    // Abrir caixa é do principal: aceitar aqui deixaria o operador com uma
    // operação salva que nunca teria como ser entregue.
    expect(
      stack.gateway.handlesWrite('POST', '/cash-register/open/', const {}),
      isFalse,
    );
    // A pesagem do próprio secundário fecha aqui, mesmo com o Principal
    // respondendo: a balança está na porta serial DELE, e o pedido é montado
    // com a cópia local do cardápio e das comandas. Quem entrega ao Principal
    // é a fila, como em qualquer outra venda. Antes isto era recusado, e a
    // balança de um Caixa Secundário pesava sem nunca fechar a comanda.
    stack.gateway.connectivity = () => true;
    expect(
      stack.gateway.handlesWrite(
        'POST',
        '/scales/bal-1/checkout-command/',
        const {},
      ),
      isTrue,
    );
  });

  test('sem sessão vinculada, nenhuma rota é atendida localmente', () {
    stack.gateway.clearSession();

    for (final path in [...locais.keys, ...servidor.keys]) {
      expect(stack.gateway.handlesRead(path), isFalse, reason: path);
      expect(
        stack.gateway.handlesWrite('POST', path, const {}),
        isFalse,
        reason: path,
      );
    }
  });
}
