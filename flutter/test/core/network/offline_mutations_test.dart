import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/offline_mutations.dart';

const _order = '/orders/8f14e45f-ceea-4a12';

void main() {
  group('pesagem no Caixa Secundario', () {
    // A balanca esta na porta serial DO secundario. Ele le o peso, monta o
    // pedido com a copia local do cardapio e das comandas e a fila entrega ao
    // Principal -- e um pedido normal, so que com alguns passos antes.
    const checkout = '/scales/8f14e45f-ceea-4a12/checkout-command/';

    test('o Principal aceita o fechamento vindo pela rede local', () {
      expect(OfflineMutations.isRelayable('POST', checkout), isTrue);
    });

    test('mas o ApiClient nao enfileira uma pesagem por conta propria', () {
      // Quem coloca a pesagem na fila e o armazenamento local, ao montar o
      // pedido com o peso no corpo (o backend materializa a leitura no
      // replay). Enfileirar aqui criaria uma leitura que nunca aconteceu
      // naquele instante.
      expect(OfflineMutations.isQueueable('POST', checkout), isFalse);
    });
  });

  group('cadastro de equipamento do proprio terminal', () {
    // Um Caixa Secundario tem impressora e balanca ligadas nele. Corrigir a
    // porta, o IP ou o setor era impossivel la: a rota nao passava pela fila
    // nem pelo relay, entao a tela salvava contra a nuvem (que o secundario
    // nao alcanca) e o operador ficava sem conseguir configurar o proprio
    // equipamento.
    const printer = '/printers/8f14e45f-ceea-4a12/';
    const scale = '/scales/9a25b7c1-3f42-4d88/';

    test('editar impressora e balanca espera na fila e vai ao Principal', () {
      expect(OfflineMutations.isQueueable('PATCH', printer), isTrue);
      expect(OfflineMutations.isQueueable('PATCH', scale), isTrue);
      expect(OfflineMutations.isRelayable('PATCH', printer), isTrue);
      expect(OfflineMutations.isRelayable('PATCH', scale), isTrue);
    });

    test('criar equipamento continua sendo operacao de servidor', () {
      // Um cadastro novo precisa do id definitivo antes de qualquer terminal
      // apontar para ele.
      expect(OfflineMutations.isQueueable('POST', '/printers/'), isFalse);
      expect(OfflineMutations.isQueueable('POST', '/scales/'), isFalse);
    });

    test('a nota de teste nao entra na fila', () {
      // Testar a impressora e um diagnostico do agora: enfileirar para depois
      // nao diz nada sobre o equipamento.
      expect(
        OfflineMutations.isQueueable('POST', '${printer}test-connection/'),
        isFalse,
      );
    });
  });

  group('operações que podem esperar na fila', () {
    test('o atendimento inteiro cabe offline', () {
      expect(OfflineMutations.isQueueable('POST', '/orders/'), isTrue);
      // Abrir por comanda segue a mesma regra da mesa: é o começo do
      // atendimento e recusar aqui travaria a venda enquanto a rede não volta.
      expect(
        OfflineMutations.isQueueable('POST', '/orders/open-command/'),
        isTrue,
      );
      expect(OfflineMutations.isQueueable('POST', '$_order/items/'), isTrue);
      expect(
        OfflineMutations.isQueueable(
          'DELETE',
          '$_order/items/9a25b7c1-3f42-4d88/void/',
        ),
        isTrue,
      );
      expect(OfflineMutations.isQueueable('POST', '$_order/close/'), isTrue);
      expect(
        OfflineMutations.isQueueable('POST', '$_order/send-to-kitchen/'),
        isTrue,
      );
      expect(OfflineMutations.isQueueable('POST', '$_order/pay/'), isTrue);
      // O garçom materializa o rascunho junto com o primeiro item — mesmo
      // início de atendimento que `/orders/`.
      expect(
        OfflineMutations.isQueueable('POST', '/orders/create-with-item/'),
        isTrue,
      );
    });

    test('cadastro de cliente entra, com criação e edição', () {
      expect(OfflineMutations.isQueueable('POST', '/customers/'), isTrue);
      expect(
        OfflineMutations.isQueueable('PATCH', '/customers/abc-123/'),
        isTrue,
      );
    });

    test('o que exige servidor fica de fora', () {
      // Impressão não pode "sair mais tarde", e caixa envolve conferência de
      // valores que o terminal não resolve.
      for (final path in [
        '$_order/print/',
        '/cash-register/open/',
        '/cash-register/abc-123/close/',
        '/print-jobs/abc-123/mark-printed/',
      ]) {
        expect(
          OfflineMutations.isQueueable('POST', path),
          isFalse,
          reason: '$path não deveria entrar na fila',
        );
      }
    });

    test('métodos e rotas fora do formato são recusados', () {
      expect(OfflineMutations.isQueueable('GET', '/orders/'), isFalse);
      expect(OfflineMutations.isQueueable('PUT', '/orders/'), isFalse);
      expect(OfflineMutations.isQueueable('POST', '/orders'), isFalse);
      expect(OfflineMutations.isQueueable('POST', '$_order/cancel/'), isFalse);
      // Travessia de diretório não passa nem no caminho local.
      expect(
        OfflineMutations.isQueueable('POST', '/orders/../admin/close/'),
        isFalse,
      );
    });

    test('um ID curto do servidor não impede a venda', () {
      // A fila monta o caminho a partir de um ID que o servidor devolveu.
      // Exigir tamanho mínimo aqui só deixaria o operador sem vender.
      expect(OfflineMutations.isQueueable('POST', '/orders/7/close/'), isTrue);
      expect(OfflineMutations.isQueueable('POST', '/orders/7/items/'), isTrue);
    });
  });

  group('operações entregues ao Caixa Principal', () {
    test('tudo do atendimento passa pelo principal', () {
      // Esta é a correção: fechar e pagar eram recusados pelo relay e iam do
      // caixa cliente direto para a nuvem, contornando o principal.
      for (final path in [
        '$_order/close/',
        '$_order/send-to-kitchen/',
        '$_order/pay/',
        '$_order/items/',
        '/orders/',
        '/orders/open-command/',
        // Regressão: faltava aqui, então o Caixa Principal recusava a
        // criação vinda do app do garçom com "Envelope da operação local
        // inválido" — só pedidos já existentes funcionavam.
        '/orders/create-with-item/',
      ]) {
        expect(
          OfflineMutations.isRelayable('POST', path),
          isTrue,
          reason: '$path deveria passar pelo Caixa Principal',
        );
      }
    });

    test('cadastro de cliente não precisa do principal', () {
      expect(OfflineMutations.isRelayable('POST', '/customers/'), isFalse);
      expect(
        OfflineMutations.isRelayable('PATCH', '/customers/abc-123/'),
        isFalse,
      );
    });

    test('o principal exige um identificador com cara de identificador', () {
      // Vindo da LAN o formato é verificado com rigor: aqui o principal
      // executa o que outra máquina pediu.
      expect(OfflineMutations.isRelayable('POST', '/orders/7/close/'), isFalse);
      expect(
        OfflineMutations.isRelayable('POST', '/orders/../etc/close/'),
        isFalse,
      );
      expect(OfflineMutations.isRelayable('POST', '$_order/close/'), isTrue);
    });

    test('o relay nunca aceita mais do que a fila aceitaria', () {
      const candidates = [
        ('POST', '/orders/'),
        ('POST', '/customers/'),
        ('POST', '$_order/pay/'),
        ('POST', '$_order/print/'),
        ('GET', '/orders/'),
        ('POST', '/cash-register/open/'),
      ];
      for (final (method, path) in candidates) {
        if (OfflineMutations.isRelayable(method, path)) {
          expect(
            OfflineMutations.isQueueable(method, path),
            isTrue,
            reason: '$method $path é relayable mas não é enfileirável',
          );
        }
      }
    });
  });

  group('criação de recurso', () {
    test('só o que gera um ID novo precisa de ID temporário', () {
      expect(OfflineMutations.createsResource('POST', '/orders/'), isTrue);
      expect(
        OfflineMutations.createsResource('POST', '$_order/items/'),
        isTrue,
      );
      expect(OfflineMutations.createsResource('POST', '/customers/'), isTrue);
      // Abrir uma comanda cria o pedido, então precisa de ID temporário para
      // os itens lançados offline se pendurarem nele.
      expect(
        OfflineMutations.createsResource('POST', '/orders/open-command/'),
        isTrue,
      );
      expect(
        OfflineMutations.createsResource(
          'POST',
          '/orders/create-with-item/',
        ),
        isTrue,
      );

      // Fechar muda um pedido existente; pagar cria um Payment reconciliável.
      expect(
        OfflineMutations.createsResource('POST', '$_order/close/'),
        isFalse,
      );
      expect(OfflineMutations.createsResource('POST', '$_order/pay/'), isTrue);
      expect(
        OfflineMutations.createsResource('PATCH', '/customers/abc-123/'),
        isFalse,
      );
    });
  });
}
