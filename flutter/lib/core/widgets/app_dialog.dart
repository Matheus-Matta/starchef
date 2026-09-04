import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../theme/app_theme.dart';

/// Diálogo padrão do PDV, renderizado pelo flutter-shadcn-ui.
///
/// A API acompanha a parte do [AlertDialog] usada pelo projeto para que todos
/// os fluxos possam compartilhar a mesma superfície sem duplicar layout.
class AppDialog extends StatelessWidget {
  const AppDialog({
    super.key,
    this.title,
    this.content,
    this.actions = const [],
    this.scrollable = false,
    this.maxWidth = 920,
    this.destructive = false,
  });

  final Widget? title;
  final Widget? content;
  final List<Widget> actions;
  final bool scrollable;
  final double maxWidth;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final media = MediaQuery.of(context);
    final effectiveMaxWidth = math.min(
      maxWidth,
      math.max(240.0, media.size.width - 32),
    );
    final constraints = BoxConstraints(
      maxWidth: effectiveMaxWidth,
      maxHeight: math.max(200.0, media.size.height - 32),
    );
    final dialog = destructive ? ShadDialog.alert : ShadDialog.new;
    Widget? materialChild(Widget? child) => child == null
        ? null
        : Material(type: MaterialType.transparency, child: child);

    return dialog(
      title: materialChild(title),
      child: materialChild(content),
      actions: actions.map((action) => materialChild(action)!).toList(),
      scrollable: scrollable,
      constraints: constraints,
      radius: AppTheme.radius,
      shadows: const [],
      crossAxisAlignment: CrossAxisAlignment.stretch,
      actionsPinned: true,
      actionsAxis: effectiveMaxWidth < 420 ? Axis.vertical : Axis.horizontal,
      actionsGap: 8,
    );
  }
}
