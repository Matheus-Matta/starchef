import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shadcn_ui/shadcn_ui.dart';
import 'package:starchef_garcom/core/theme/app_theme.dart';
import 'package:starchef_garcom/core/widgets/shadcn_layout.dart';

/// Trava o que a biblioteca de layout promete: que os blocos de todas as telas
/// saiam do MESMO tema, com a MESMA altura e a MESMA cor.
///
/// Sem isto, o alinhamento volta a depender de alguém lembrar do número certo
/// ao escrever a próxima tela — que foi exatamente como ele se perdeu antes.
void main() {
  /// A mesma montagem do `main.dart`: Material por baixo, tokens shadcn por
  /// cima. Um teste sobre um tema diferente do que roda no aparelho não
  /// protegeria nada.
  Widget host(Widget child) => MaterialApp(
    theme: AppTheme.materialLight(),
    home: ShadTheme(
      data: AppTheme.shadLight(),
      child: Scaffold(body: child),
    ),
  );

  group('altura dos controles', () {
    testWidgets('botão mede exatamente AppTheme.controlHeight', (tester) async {
      await tester.pumpWidget(
        host(
          Center(
            child: FilledButton(onPressed: () {}, child: const Text('Enviar')),
          ),
        ),
      );
      expect(
        tester.getSize(find.byType(FilledButton)).height,
        AppTheme.controlHeight,
      );
    });

    testWidgets('campo nunca fica mais baixo que o botão vizinho', (
      tester,
    ) async {
      await tester.pumpWidget(
        host(
          const Padding(
            padding: EdgeInsets.all(16),
            child: TextField(decoration: InputDecoration(hintText: 'Buscar')),
          ),
        ),
      );
      expect(
        tester.getSize(find.byType(TextField)).height,
        greaterThanOrEqualTo(AppTheme.controlHeight),
      );
    });
  });

  group('faixa de aviso', () {
    testWidgets('mostra o recado e a ação', (tester) async {
      var tapped = false;
      await tester.pumpWidget(
        host(
          AppNotice(
            message: 'Sem conexão com o caixa.',
            actionLabel: 'Tentar agora',
            onAction: () => tapped = true,
          ),
        ),
      );
      expect(find.text('Sem conexão com o caixa.'), findsOneWidget);
      await tester.tap(find.text('Tentar agora'));
      expect(tapped, isTrue);
    });

    testWidgets('a gravidade vem da paleta compartilhada', (tester) async {
      await tester.pumpWidget(
        host(
          const AppNotice(
            tone: AppNoticeTone.danger,
            icon: Icons.error_outline,
            message: 'Operação recusada.',
          ),
        ),
      );
      final icon = tester.widget<Icon>(find.byIcon(Icons.error_outline));
      expect(icon.color, AppColors.danger);
    });
  });

  testWidgets('selo de estado mostra o rótulo', (tester) async {
    await tester.pumpWidget(
      host(
        const Center(
          child: AppStatusBadge(label: '3 a enviar', color: AppColors.warning),
        ),
      ),
    );
    expect(find.text('3 a enviar'), findsOneWidget);
  });

  group('tela vazia', () {
    testWidgets('mostra motivo e saída', (tester) async {
      await tester.pumpWidget(
        host(
          AppEmptyState(
            icon: Icons.receipt_long_outlined,
            title: 'Nenhum pedido aberto',
            description: 'Toque em "Novo pedido".',
            action: FilledButton(
              onPressed: () {},
              child: const Text('Tentar de novo'),
            ),
          ),
        ),
      );
      expect(find.text('Nenhum pedido aberto'), findsOneWidget);
      expect(find.text('Toque em "Novo pedido".'), findsOneWidget);
      expect(find.text('Tentar de novo'), findsOneWidget);
    });

    testWidgets('em modo rolável, o puxar-para-atualizar chega no gesto', (
      tester,
    ) async {
      var refreshed = false;
      await tester.pumpWidget(
        host(
          RefreshIndicator(
            onRefresh: () async => refreshed = true,
            child: const AppEmptyState(
              scrollable: true,
              icon: Icons.wifi_off,
              title: 'Não foi possível carregar',
              description: 'O Caixa Principal não respondeu.',
            ),
          ),
        ),
      );
      // Sem `scrollable`, não há nada rolável embaixo do dedo e o gesto morre
      // aqui — era a única forma de tentar de novo sair e voltar da tela.
      await tester.fling(
        find.text('Não foi possível carregar'),
        const Offset(0, 300),
        1000,
      );
      await tester.pumpAndSettle();
      expect(refreshed, isTrue);
    });
  });

  testWidgets('botão de formulário troca ícone por progresso ao trabalhar', (
    tester,
  ) async {
    await tester.pumpWidget(
      host(
        const Center(
          child: AppSubmitButton(
            label: 'Entrar',
            busyLabel: 'Entrando...',
            icon: Icons.login,
            busy: true,
            onPressed: _noop,
          ),
        ),
      ),
    );
    expect(find.text('Entrando...'), findsOneWidget);
    expect(find.byIcon(Icons.login), findsNothing);
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });
}

void _noop() {}
