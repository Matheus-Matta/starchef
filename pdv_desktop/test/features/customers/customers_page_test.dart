import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_pdv_desktop/core/theme/app_theme.dart';
import 'package:starchef_pdv_desktop/features/customers/presentation/customer_form_dialog.dart';

/// A modal de cadastro é a MESMA nos dois lugares que a abrem — o fluxo do
/// pedido e a tela de clientes. O que estes testes fixam é o que ela promete a
/// quem está digitando: nada se perde quando o servidor recusa.
void main() {
  Future<void> abrir(
    WidgetTester tester, {
    required Future<Map<String, dynamic>> Function(Map<String, dynamic>) onSubmit,
    void Function(Object)? onError,
    Map<String, dynamic>? existing,
    String confirmLabel = 'Cadastrar',
  }) async {
    // `AppDialog` e um `ShadDialog`: sem o tema do shadcn a arvore nao monta.
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.dark(),
        builder: (context, child) =>
            ShadTheme(data: AppTheme.shadDark(), child: child!),
        home: Scaffold(
          body: CustomerFormDialog(
            onSubmit: onSubmit,
            onError: onError ?? (_) {},
            existing: existing,
            confirmLabel: confirmLabel,
            restaurantId: 'rest-1',
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  testWidgets('exige nome e telefone antes de chamar o servidor', (
    tester,
  ) async {
    var chamou = false;
    await abrir(
      tester,
      onSubmit: (_) async {
        chamou = true;
        return const {};
      },
    );

    await tester.tap(find.text('Cadastrar'));
    await tester.pumpAndSettle();

    // O servidor não é consultado para descobrir que falta o nome: a recusa
    // acontece no aparelho, sem rede e sem espera.
    expect(chamou, isFalse);
    expect(find.text('Informe o nome do cliente.'), findsOneWidget);
    expect(find.text('Informe o telefone.'), findsOneWidget);
  });

  testWidgets('manda o restaurante junto do cadastro', (tester) async {
    Map<String, dynamic>? enviado;
    await abrir(
      tester,
      onSubmit: (corpo) async {
        enviado = corpo;
        return {...corpo, 'id': 'c-1'};
      },
    );

    await tester.enterText(find.byType(TextFormField).at(0), 'Maria Silva');
    await tester.enterText(find.byType(TextFormField).at(1), '11999990000');
    await tester.tap(find.text('Cadastrar'));
    await tester.pumpAndSettle();

    expect(enviado?['name'], 'Maria Silva');
    expect(enviado?['phone'], '11999990000');
    // Sem o restaurante o cliente nasce órfão e não aparece na lista do
    // terminal que o cadastrou.
    expect(enviado?['restaurant'], 'rest-1');
  });

  testWidgets('recusa do servidor NÃO apaga o que foi digitado', (
    tester,
  ) async {
    Object? recebido;
    await abrir(
      tester,
      onSubmit: (_) async => throw StateError('CPF já cadastrado'),
      onError: (falha) => recebido = falha,
    );

    await tester.enterText(find.byType(TextFormField).at(0), 'Maria Silva');
    await tester.enterText(find.byType(TextFormField).at(1), '11999990000');
    await tester.tap(find.text('Cadastrar'));
    await tester.pumpAndSettle();

    expect(recebido, isA<StateError>());
    // O ponto do teste: a modal continua aberta com o texto no lugar. Fechar
    // aqui obrigaria o operador a digitar tudo de novo para corrigir um campo.
    expect(find.text('Maria Silva'), findsOneWidget);
    expect(find.text('11999990000'), findsOneWidget);
    expect(find.text('Cadastrar'), findsOneWidget);
  });

  testWidgets('editando, abre com os dados e muda o título', (tester) async {
    await abrir(
      tester,
      onSubmit: (corpo) async => corpo,
      existing: const {
        'id': 'c-9',
        'name': 'João',
        'phone': '11888887777',
        'email': 'joao@exemplo.com',
      },
      confirmLabel: 'Salvar',
    );

    expect(find.text('Editar cliente'), findsOneWidget);
    expect(find.text('João'), findsOneWidget);
    expect(find.text('11888887777'), findsOneWidget);
    expect(find.text('joao@exemplo.com'), findsOneWidget);
    expect(find.text('Salvar'), findsOneWidget);
  });
}
