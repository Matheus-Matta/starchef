import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../theme/app_theme.dart';

class AppPageHeader extends StatelessWidget {
  const AppPageHeader({
    super.key,
    required this.title,
    this.description,
    this.leading,
    this.actions = const [],
  });

  final String title;
  final String? description;
  final Widget? leading;
  final List<Widget> actions;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.fromLTRB(24, 20, 24, 18),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border.all(color: scheme.outlineVariant),
        borderRadius: AppTheme.radius,
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final compact = constraints.maxWidth < 640;
          final identity = Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (leading != null) ...[leading!, const SizedBox(width: 12)],
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleLarge?.copyWith(
                        fontWeight: FontWeight.w800,
                        letterSpacing: -.2,
                      ),
                    ),
                    if (description != null) ...[
                      const SizedBox(height: 3),
                      Text(
                        description!,
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          );
          if (compact) {
            return Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                identity,
                if (actions.isNotEmpty) ...[
                  const SizedBox(height: 14),
                  Wrap(spacing: 8, runSpacing: 8, children: actions),
                ],
              ],
            );
          }
          return Row(
            children: [
              Expanded(child: identity),
              if (actions.isNotEmpty) ...[
                const SizedBox(width: 16),
                Flexible(
                  child: Wrap(
                    alignment: WrapAlignment.end,
                    spacing: 8,
                    runSpacing: 8,
                    children: actions,
                  ),
                ),
              ],
            ],
          );
        },
      ),
    );
  }
}

class AppPageScaffold extends StatelessWidget {
  const AppPageScaffold({
    super.key,
    required this.title,
    required this.body,
    this.description,
    this.leading,
    this.actions = const [],
    this.padding = const EdgeInsets.all(16),
  });

  final String title;
  final String? description;
  final Widget body;
  final Widget? leading;
  final List<Widget> actions;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: ColoredBox(
          color: scheme.surfaceContainerLowest,
          child: Padding(
            padding: padding,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                AppPageHeader(
                  title: title,
                  description: description,
                  leading: leading,
                  actions: actions,
                ),
                const SizedBox(height: 12),
                Expanded(child: body),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class AppSection extends StatelessWidget {
  const AppSection({
    super.key,
    this.title,
    this.description,
    this.trailing,
    required this.child,
    this.padding = const EdgeInsets.all(18),
  });

  final String? title;
  final String? description;
  final Widget? trailing;
  final Widget child;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
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
          padding: EdgeInsets.only(
            top: title == null && description == null ? 0 : 16,
          ),
          child: child,
        ),
      ),
    );
  }
}

class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.description,
    this.action,
  });

  final IconData icon;
  final String title;
  final String description;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 420),
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 48,
                height: 48,
                decoration: BoxDecoration(
                  color: scheme.surfaceContainer,
                  borderRadius: AppTheme.radius,
                  border: Border.all(color: scheme.outlineVariant),
                ),
                child: Icon(icon, size: 23, color: scheme.onSurfaceVariant),
              ),
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
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
              if (action != null) ...[const SizedBox(height: 18), action!],
            ],
          ),
        ),
      ),
    );
  }
}

class AppStatusBadge extends StatelessWidget {
  const AppStatusBadge({
    super.key,
    required this.label,
    this.icon,
    this.foreground,
    this.background,
    this.onPressed,
  });

  final String label;
  final IconData? icon;
  final Color? foreground;
  final Color? background;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final effectiveForeground = foreground ?? scheme.onSurfaceVariant;
    return ShadBadge.raw(
      variant: ShadBadgeVariant.outline,
      onPressed: onPressed,
      backgroundColor: background ?? scheme.surfaceContainer,
      foregroundColor: effectiveForeground,
      shape: RoundedRectangleBorder(
        borderRadius: AppTheme.radius,
        side: BorderSide(color: effectiveForeground.withValues(alpha: .2)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: effectiveForeground),
            const SizedBox(width: 5),
          ],
          Text(
            label,
            style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

/// Mantém campos relacionados lado a lado em telas amplas e os empilha quando
/// cada controle ficaria estreito demais para rótulos, sufixos e validações.
class AppResponsiveFields extends StatelessWidget {
  const AppResponsiveFields({
    super.key,
    required this.children,
    this.breakpoint = 560,
    this.spacing = 16,
    this.flex = const [],
  });

  final List<Widget> children;
  final double breakpoint;
  final double spacing;
  final List<int> flex;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        if (constraints.maxWidth < breakpoint) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              for (var index = 0; index < children.length; index++) ...[
                if (index > 0) SizedBox(height: spacing),
                children[index],
              ],
            ],
          );
        }
        return Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var index = 0; index < children.length; index++) ...[
              if (index > 0) SizedBox(width: spacing),
              Expanded(
                flex: index < flex.length ? flex[index] : 1,
                child: children[index],
              ),
            ],
          ],
        );
      },
    );
  }
}
