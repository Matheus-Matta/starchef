import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';

/// Moldura das telas de entrada (login e pareamento).
///
/// As duas são a mesma cena para quem usa — abrir o app e chegar até os
/// pedidos — então compartilham marca, cartão, erro e rodapé em vez de manter
/// dois layouts que envelhecem separados.
class AuthScaffold extends StatelessWidget {
  const AuthScaffold({
    super.key,
    required this.title,
    required this.subtitle,
    required this.child,
    this.error,
    this.footnote,
    this.action,
  });

  final String title;
  final String subtitle;
  final Widget child;
  final String? error;
  final String? footnote;

  /// Ação secundária abaixo do cartão (ex.: "Sair" na tela de pareamento).
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(20),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 460),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Align escapa do stretch da Column: sem isso a logo seria
                  // esticada para os 460 de largura do cartão.
                  Align(
                    child: ClipRRect(
                      borderRadius: AppTheme.radius,
                      child: Image.asset(
                        'assets/icon/master.png',
                        height: 64,
                        width: 64,
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    title,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 20),
                  ShadCard(
                    radius: AppTheme.radius,
                    columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                    child: child,
                  ),
                  if (error != null) ...[
                    const SizedBox(height: 14),
                    _ErrorBanner(message: error!),
                  ],
                  if (action != null) ...[
                    const SizedBox(height: 12),
                    action!,
                  ],
                  if (footnote != null) ...[
                    const SizedBox(height: 14),
                    Text(
                      footnote!,
                      textAlign: TextAlign.center,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: scheme.errorContainer,
        borderRadius: AppTheme.radius,
        border: Border.all(color: scheme.error.withValues(alpha: .4)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.error_outline, color: scheme.error, size: 20),
          const SizedBox(width: 10),
          Expanded(
            child: SelectableText(
              message,
              style: TextStyle(color: scheme.onErrorContainer, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}
