import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/app_theme.dart';
import 'app_error.dart';
import 'error_center.dart';

/// Disponibiliza o [ErrorCenter] para a árvore de widgets.
class ErrorCenterScope extends InheritedNotifier<ErrorCenter> {
  const ErrorCenterScope({
    super.key,
    required ErrorCenter center,
    required super.child,
  }) : super(notifier: center);

  static ErrorCenter of(BuildContext context) {
    final scope = context
        .dependOnInheritedWidgetOfExactType<ErrorCenterScope>();
    assert(scope?.notifier != null, 'ErrorCenterScope ausente na árvore.');
    return scope!.notifier!;
  }

  /// Versão que não cria dependência de rebuild — para uso em callbacks.
  static ErrorCenter read(BuildContext context) {
    final scope = context.getInheritedWidgetOfExactType<ErrorCenterScope>();
    assert(scope?.notifier != null, 'ErrorCenterScope ausente na árvore.');
    return scope!.notifier!;
  }
}

/// Sobrepõe os alertas globais ao conteúdo do aplicativo.
///
/// Os cartões ficam no topo, acima de qualquer tela, e permanecem até o
/// operador fechá-los no `X`. Eles não bloqueiam a interface: o operador pode
/// corrigir os dados com o alerta ainda visível.
class AppErrorHost extends StatelessWidget {
  const AppErrorHost({super.key, required this.center, required this.child});

  final ErrorCenter center;
  final Widget child;

  @override
  Widget build(BuildContext context) => ErrorCenterScope(
    center: center,
    child: Stack(
      children: [
        child,
        // Os cartões precisam de um `Overlay` próprio.
        //
        // Este host é montado no `builder` do `MaterialApp`, ou seja acima do
        // Navigator — que é justamente quem fornece o Overlay do aplicativo.
        // Sem um Overlay aqui, qualquer widget que dependa dele (`Tooltip`,
        // menus, seleção de texto) lança exceção ao ser construído, e o alerta
        // de erro deixaria de aparecer exatamente quando é mais necessário.
        //
        // O Stack interno do Overlay não absorve toques em áreas vazias, então
        // o resto da interface continua clicável por baixo.
        Positioned.fill(
          child: Overlay(
            initialEntries: [
              OverlayEntry(
                builder: (context) => Positioned(
                  top: 12,
                  right: 12,
                  child: SafeArea(
                    child: ListenableBuilder(
                      listenable: center,
                      builder: (context, _) => Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          for (final error in center.visible)
                            Padding(
                              padding: const EdgeInsets.only(bottom: 10),
                              child: AppErrorCard(
                                error: error,
                                onClose: () => center.dismiss(error),
                              ),
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ],
    ),
  );
}

/// Cartão de erro: só título e mensagem na tela, com botão de copiar e de
/// fechar.
///
/// O resto (origem, código, horário, ação recomendada, detalhe técnico) só
/// existe no texto copiado — [AppError.toClipboardText] — para não sobrecarregar
/// o operador com informação que ele não pediu; quem precisa desses detalhes
/// para abrir um chamado clica em copiar.
class AppErrorCard extends StatelessWidget {
  const AppErrorCard({super.key, required this.error, required this.onClose});

  final AppError error;
  final VoidCallback onClose;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (accent, icon) = switch (error.severity) {
      AppErrorSeverity.failure => (scheme.error, Icons.error_outline),
      AppErrorSeverity.warning => (
        const Color(0xFF9A5B00),
        Icons.warning_amber_outlined,
      ),
      AppErrorSeverity.info => (scheme.primary, Icons.info_outline),
    };

    return Material(
      elevation: 0,
      borderRadius: AppTheme.radius,
      color: scheme.surface,
      shadowColor: Colors.transparent,
      child: Container(
        width: 360,
        padding: const EdgeInsets.fromLTRB(14, 12, 8, 12),
        decoration: BoxDecoration(
          borderRadius: AppTheme.radius,
          border: Border.all(color: accent.withValues(alpha: .45)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(icon, color: accent, size: 22),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    error.title,
                    style: TextStyle(
                      color: accent,
                      fontWeight: FontWeight.w900,
                      fontSize: 14,
                    ),
                  ),
                ),
                IconButton(
                  tooltip: 'Copiar detalhes',
                  onPressed: () => _copy(context, error),
                  icon: const Icon(Icons.copy_all_outlined, size: 18),
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints.tightFor(
                    width: 32,
                    height: 32,
                  ),
                ),
                IconButton(
                  // Requisito do backlog: todo erro visível fecha imediatamente.
                  tooltip: 'Fechar alerta',
                  onPressed: onClose,
                  icon: const Icon(Icons.close, size: 19),
                  visualDensity: VisualDensity.compact,
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints.tightFor(
                    width: 34,
                    height: 34,
                  ),
                ),
              ],
            ),
            Padding(
              padding: const EdgeInsets.only(left: 32, right: 6, top: 2),
              child: SelectableText(
                error.message,
                style: const TextStyle(fontSize: 13, height: 1.35),
              ),
            ),
          ],
        ),
      ),
    );
  }

  static Future<void> _copy(BuildContext context, AppError error) async {
    await Clipboard.setData(ClipboardData(text: error.toClipboardText()));
    if (!context.mounted) return;
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      const SnackBar(
        content: Text('Detalhes copiados.'),
        duration: Duration(milliseconds: 1200),
      ),
    );
  }
}
