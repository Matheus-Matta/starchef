import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/auth/domain/auth_session.dart';

/// O perfil "Balança" entra no PDV direto na Balança Rápida.
///
/// Ele só opera a estação de pesagem: passar pela tela de venda seria mostrar
/// caixa, pedidos e comandas a quem não deve mexer neles.
void main() {
  AuthUser usuario(String? perfil, [List<String> permissoes = const []]) =>
      AuthUser(
        id: 'u1',
        username: 'balanca',
        name: 'Balança',
        profileType: perfil,
        permissions: permissoes,
      );

  test('o perfil Balança abre direto na Balança Rápida', () {
    final balanca = usuario('scale', ['scale.operate', 'menu.view']);

    expect(balanca.isScaleOperator, isTrue);
    expect(balanca.canAccessCash, isFalse);
    expect(balanca.canViewOrders, isFalse);
    expect(balanca.canProcessPayments, isFalse);
  });

  test('caixa e gerente continuam abrindo o PDV inteiro', () {
    expect(usuario('cashier', ['scale.operate']).isScaleOperator, isFalse);
    expect(usuario('manager').isScaleOperator, isFalse);
    expect(usuario(null).isScaleOperator, isFalse);
  });
}
