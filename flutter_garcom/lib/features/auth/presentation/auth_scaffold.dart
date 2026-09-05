import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

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
    final theme = Theme.of(context);
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
                    style: theme.textTheme.headlineSmall?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    subtitle,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 20),
                  AppSection(child: child),
                  if (error != null) ...[
                    const SizedBox(height: 14),
                    AppNotice(
                      tone: AppNoticeTone.danger,
                      icon: Icons.error_outline,
                      message: error!,
                      // O erro de entrada é técnico (host, chave, token) e
                      // acaba no WhatsApp do suporte: precisa ser copiável.
                      selectable: true,
                    ),
                  ],
                  if (action != null) ...[const SizedBox(height: 12), action!],
                  if (footnote != null) ...[
                    const SizedBox(height: 14),
                    Text(
                      footnote!,
                      textAlign: TextAlign.center,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurfaceVariant,
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
