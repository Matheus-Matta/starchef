import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/offline_mutations.dart';

const _order = '/orders/8f14e45f-ceea-4a12';

void main() {
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
