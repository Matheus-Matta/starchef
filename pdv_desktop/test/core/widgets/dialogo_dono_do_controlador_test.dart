import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/widgets/responsive_scale.dart';

/// Quem é dono dos `TextEditingController` de um diálogo.
///
/// Dois defeitos reais saíram daqui, os dois na autorização de sangria e
/// suprimento, e os dois REPRODUZIDOS antes de corrigidos.
///
/// **1. Limpar um campo focado antes de fechar.**
///
/// ```dart
/// await autorizarNoServidor();  // lacuna assíncrona: fora de um quadro
/// senha.clear();                // marca o EditableText como sujo AGORA
/// Navigator.pop(ctx);           // e o tira da árvore em seguida
/// ```
///
/// O campo tem `autofocus`, então o cursor está piscando — e o cursor é um
/// `AnimatedBuilder`. `clear()` fora de um quadro suja esse elemento dentro do
/// escopo de build do `LayoutBuilder` (o `ResponsiveScale` envolve o app
/// inteiro); o `pop` o tira da árvore, e quando o layout roda o callback do
/// `LayoutBuilder` o elemento sujo já não é descendente dele:
///
///   Tried to build dirty widget in the wrong build scope.
///   The root of the build scope was: LayoutBuilder
///   The offending element ... was: AnimatedBuilder
///
/// **2. Descartar o controlador cedo demais.**
///
/// ```dart
/// try {
///   await showDialog(...);
/// } finally {
///   senha.dispose();   // ← a animação de saída AINDA está rodando
/// }
/// ```
///
/// `await showDialog` volta quando a rota é DESEMPILHADA, não quando ela
/// termina de sair. O campo continua na tela por alguns quadros, apontando
/// para um controlador morto — "A TextEditingController was used after being
/// disposed", e a árvore meio desmontada logo depois
/// (`'_dependents.isEmpty': is not true`).
///
/// **A forma certa, que este teste guarda:** o diálogo é um widget com estado,
/// cria os controladores no `initState` e os descarta no `dispose` — que o
/// Flutter só chama depois que a rota some de verdade. Ninguém de fora cria,
/// limpa ou descarta nada.
void main() {
  testWidgets('o diálogo dono dos controladores fecha limpo', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    String? devolvido;

    await tester.pumpWidget(
      MaterialApp(
        // O `LayoutBuilder` que envolve o app inteiro faz parte do cenário: é
        // o escopo de build separado dele que transforma um elemento sujo em
        // tela vermelha.
        builder: (context, child) => ResponsiveScale(child: child!),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: ElevatedButton(
                onPressed: () async {
                  devolvido = await showDialog<String>(
                    context: context,
                    builder: (_) => const _FormularioDeAutorizacao(),
                  );
                },
                child: const Text('abrir'),
              ),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('abrir'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Autorizar'));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    // E o valor digitado chega a quem abriu: lido ANTES do `pop`, não depois.
    expect(devolvido, 'segredo');
  });
}

class _FormularioDeAutorizacao extends StatefulWidget {
  const _FormularioDeAutorizacao();

  @override
  State<_FormularioDeAutorizacao> createState() =>
      _FormularioDeAutorizacaoState();
}

class _FormularioDeAutorizacaoState extends State<_FormularioDeAutorizacao> {
  final _senha = TextEditingController(text: 'segredo');
  var _ocupado = false;

  @override
  void dispose() {
    _senha.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    content: SizedBox(
      width: 420,
      child: TextFormField(
        controller: _senha,
        autofocus: true,
        obscureText: true,
      ),
    ),
    actions: [
      FilledButton(
        onPressed: _ocupado
            ? null
            : () async {
                setState(() => _ocupado = true);
                // A ida ao servidor: é ela que nos tira do quadro.
                await Future<void>.delayed(Duration.zero);
                if (!mounted) return;
                Navigator.pop(context, _senha.text);
              },
        child: const Text('Autorizar'),
      ),
    ],
  );
}
