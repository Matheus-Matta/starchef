import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../theme/app_theme.dart';

/// As superfícies onde o conteúdo mora: o cartão de uma seção, o título de
/// um trecho de lista e a tela que não tem nada para mostrar.

/// Cartão com título e descrição opcionais — o mesmo `AppSection` do desktop.
class AppSection extends StatelessWidget {
  const AppSection({
    super.key,
    required this.child,
    this.title,
    this.description,
    this.trailing,
    this.padding = const EdgeInsets.all(AppTheme.gapLoose),
  });

  final Widget child;
  final String? title;
  final String? description;
  final Widget? trailing;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final hasHeader = title != null || description != null;
    return ShadCard(
      padding: padding,
      radius: AppTheme.radius,
      shadows: const [],
      columnCrossAxisAlignment: CrossAxisAlignment.stretch,
      title: title == null
          ? null
          : Row(
              children: [
                Expanded(
                  child: Text(
                    title!,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                ),
                ?trailing,
              ],
            ),
      description: description == null
          ? null
          : Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Text(
                description!,
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
            ),
      child: Material(
        type: MaterialType.transparency,
        child: Padding(
          padding: EdgeInsets.only(top: hasHeader ? AppTheme.gap : 0),
          child: child,
        ),
      ),
    );
  }
}

/// Tela (ou lista) sem nada para mostrar, com o motivo e a saída.
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.description,
    this.action,
    this.scrollable = false,
  });

  final IconData icon;
  final String title;
  final String description;
  final Widget? action;

  /// Deixa a mensagem rolar mesmo sem conteúdo que transborde.
  ///
  /// É o que mantém o "puxar para atualizar" funcionando quando a lista está
  /// vazia: sem algo rolável embaixo, o gesto não chega ao `RefreshIndicator`
  /// e a única forma de tentar de novo seria sair e voltar da tela.
  final bool scrollable;

  @override
  Widget build(BuildContext context) {
    final content = Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _Icon(icon),
              const SizedBox(height: 14),
              Text(
                title,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  fontSize: 17,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                description,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              if (action != null) ...[const SizedBox(height: 18), action!],
            ],
          ),
        ),
      ),
    );
    if (!scrollable) return content;
    return LayoutBuilder(
      builder: (context, constraints) => SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(),
        child: ConstrainedBox(
          constraints: BoxConstraints(minHeight: constraints.maxHeight),
          child: content,
        ),
      ),
    );
  }
}

class _Icon extends StatelessWidget {
  const _Icon(this.icon);

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: 48,
      height: 48,
      decoration: BoxDecoration(
        color: scheme.surfaceContainer,
        borderRadius: AppTheme.radius,
        border: Border.all(color: scheme.outlineVariant),
      ),
      child: Icon(icon, size: 23, color: scheme.onSurfaceVariant),
    );
  }
}

/// Título de um trecho de lista: "JÁ NA COZINHA", "A ENVIAR (3)".
class AppSectionLabel extends StatelessWidget {
  const AppSectionLabel({
    super.key,
    required this.label,
    this.icon,
    this.color,
  });

  final String label;
  final IconData? icon;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return Padding(
      padding: const EdgeInsets.only(top: 4, bottom: AppTheme.gap),
      child: Row(
        children: [
          if (icon != null) ...[
            Icon(icon, size: 16, color: tone),
            const SizedBox(width: AppTheme.gapTight),
          ],
          Text(
            label.toUpperCase(),
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              letterSpacing: .4,
              color: tone,
            ),
          ),
        ],
      ),
    );
  }
}
