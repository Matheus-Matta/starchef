import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// A moldura de uma tela: cabeçalho, faixas de aviso, corpo e barra de baixo.
///
/// É o que muda em relação ao desktop: lá a janela desenha o próprio
/// cabeçalho (`AppPageHeader`), aqui quem faz esse papel é a `AppBar` do
/// Material, que traz o botão de voltar e o gesto que o Android espera.

/// Moldura de uma tela inteira: título, ações, faixas de aviso, corpo e barra
/// de baixo, sempre na mesma ordem e com o mesmo respiro.
class AppPageScaffold extends StatelessWidget {
  const AppPageScaffold({
    super.key,
    required this.title,
    required this.body,
    this.actions = const [],
    this.banners = const [],
    this.bottomBar,
    this.floatingActionButton,
  });

  final String title;
  final Widget body;
  final List<Widget> actions;

  /// Faixas de estado do aparelho (atualização, dados de cache, fila offline).
  /// Ficam entre o cabeçalho e o conteúdo porque são estado contínuo, não um
  /// evento pontual — o garçom precisa vê-las sem procurar.
  final List<Widget> banners;

  final Widget? bottomBar;
  final Widget? floatingActionButton;

  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: Text(title), actions: actions),
    bottomNavigationBar: bottomBar,
    floatingActionButton: floatingActionButton,
    body: banners.isEmpty
        ? body
        : Column(
            children: [
              ...banners,
              Expanded(child: body),
            ],
          ),
  );
}

/// Barra fixa no rodapé da tela: o total e o que fazer com ele.
class AppBottomBar extends StatelessWidget {
  const AppBottomBar({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return SafeArea(
      child: Container(
        padding: const EdgeInsets.symmetric(
          horizontal: AppTheme.gapLoose,
          vertical: 12,
        ),
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border(top: BorderSide(color: scheme.outlineVariant)),
        ),
        child: child,
      ),
    );
  }
}
