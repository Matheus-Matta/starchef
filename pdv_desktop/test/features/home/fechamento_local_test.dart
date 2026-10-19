import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/auth/domain/auth_session.dart';
import 'package:starchef_pdv_desktop/features/home/data/fechamento_local.dart';

/// O fechamento calculado NO PDV, sem ida ao servidor.
///
/// Cada toque em taxa, desconto ou CPF mandava a venda inteira ao servidor
/// para simular (60 a 120 consultas) e travava a tela em "Calculando total".
/// A conta é a do servidor — e a tabela de casos é a MESMA que o teste do
/// backend lê (`test_fechamento_paridade.py`): mudou de um lado, quebra o outro.
void main() {
  final casos =
      (jsonDecode(
                File(
                  'test/fixtures/fechamento_paridade.json',
                ).readAsStringSync(),
              )
              as Map)['casos']
          as List;

  Map<String, dynamic> pedido({
    String subtotal = '25.00',
    String couponDiscount = '0.00',
    String deliveryFee = '0.00',
  }) => {
    'id': 'p1',
    'subtotal': subtotal,
    'coupon_discount': couponDiscount,
    'delivery_fee': deliveryFee,
    'total': subtotal,
  };

  for (final caso in casos.cast<Map>()) {
    test('paridade com o servidor: ${caso['nome']}', () {
      final feito = FechamentoLocal.aplicar(
        pedido(subtotal: caso['subtotal'] as String),
        {
          'service_fee_enabled': caso['taxa_ligada'],
          'discount': caso['desconto'],
        },
        percentualDaTaxa: caso['percentual'] as String,
      );

      expect(feito['service_fee'], caso['taxa']);
      expect(feito['total'], caso['total']);
    });
  }

  test('desconto maior que a conta é recusado com o motivo do servidor', () {
    expect(
      () => FechamentoLocal.aplicar(
        pedido(subtotal: '30.00', couponDiscount: '10.00'),
        {'discount': '25.00'},
        percentualDaTaxa: '10.00',
      ),
      throwsA(
        isA<FechamentoRecusado>().having(
          (e) => e.motivo,
          'motivo',
          contains('passam do subtotal'),
        ),
      ),
    );
  });

  test('desconto negativo (sinal digitado errado) é recusado', () {
    expect(
      () => FechamentoLocal.aplicar(pedido(), {
        'discount': '-5.00',
      }, percentualDaTaxa: '10.00'),
      throwsA(isA<FechamentoRecusado>()),
    );
  });

  test('CPF na nota não mexe no total', () {
    final feito = FechamentoLocal.aplicar(pedido(), {
      'fiscal_customer_cpf': '52998224725',
    }, percentualDaTaxa: '10.00');

    expect(feito['total'], '27.50');
    expect(feito['fiscal_customer_cpf'], '52998224725');
  });

  test('cupom já aceito pelo servidor continua abatendo', () {
    // O cupom foi conferido no servidor; tirar a taxa depois não pode
    // derrubar o abatimento dele.
    final feito = FechamentoLocal.aplicar(
      pedido(subtotal: '50.00', couponDiscount: '5.00'),
      {'service_fee_enabled': false},
      percentualDaTaxa: '10.00',
    );

    expect(feito['total'], '45.00');
    expect(feito['coupon_discount'], '5.00');
  });

  test('entrega entra no total, mas não na base da taxa', () {
    final feito = FechamentoLocal.aplicar(
      pedido(subtotal: '40.00', deliveryFee: '8.00'),
      const {},
      percentualDaTaxa: '10.00',
    );

    expect(feito['service_fee'], '4.00');
    expect(feito['total'], '52.00');
  });

  test('valor vindo como número (double) do carrinho vira centavos exatos', () {
    final feito = FechamentoLocal.aplicar(
      {...pedido(), 'subtotal': 0.1 + 0.2},
      const {'service_fee_enabled': false},
      percentualDaTaxa: '10.00',
    );

    expect(feito['total'], '0.30');
  });

  group('quem aprova o próprio desconto', () {
    AuthUser usuario({String? perfil, bool superusuario = false}) => AuthUser(
      id: 'u',
      username: 'u',
      name: 'u',
      profileType: perfil,
      isSuperuser: superusuario,
    );

    test('gerente, administrador e dono aprovam sem senha', () {
      for (final perfil in ['manager', 'admin', 'owner']) {
        expect(aprovaOProprioDesconto(usuario(perfil: perfil)), isTrue);
      }
      expect(aprovaOProprioDesconto(usuario(superusuario: true)), isTrue);
    });

    test('caixa e garçom precisam da senha', () {
      expect(aprovaOProprioDesconto(usuario(perfil: 'cashier')), isFalse);
      expect(aprovaOProprioDesconto(usuario(perfil: 'waiter')), isFalse);
      expect(aprovaOProprioDesconto(usuario()), isFalse);
    });
  });
}
