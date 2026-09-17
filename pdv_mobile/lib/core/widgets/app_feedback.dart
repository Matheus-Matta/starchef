import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../theme/app_theme.dart';

/// Como o app conta um estado: um selo curto ao lado do que ele descreve, ou
/// uma faixa de linha inteira no topo da tela.
///
/// Os dois usam a MESMA receita de cor — texto cheio, fundo a 12% e borda a
/// 35% da mesma tonalidade. Era essa receita que estava copiada em sete
/// lugares, cada um com uma opacidade e um respiro um pouco diferentes.

/// Selo curto de estado: "3 a enviar", "Na cozinha", "aguardando conexão".
///
/// A cor entra por [color] e vira as três camadas de uma vez — texto cheio,
/// fundo a 12% e borda a 35%. Era essa receita que estava copiada em quatro
/// lugares, cada um com uma opacidade um pouco diferente.
class AppStatusBadge extends StatelessWidget {
  const AppStatusBadge({
    super.key,
    required this.label,
    this.icon,
    this.leading,
    this.color,
    this.onPressed,
  });

  final String label;
  final IconData? icon;

  /// Substitui o ícone quando o estado precisa de movimento (um progresso
  /// circular, por exemplo).
  final Widget? leading;

  final Color? color;
  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final tone = color ?? Theme.of(context).colorScheme.onSurfaceVariant;
    return ShadBadge.raw(
      variant: ShadBadgeVariant.outline,
      onPressed: onPressed,
      backgroundColor: tone.withValues(alpha: .12),
      foregroundColor: tone,
      shape: RoundedRectangleBorder(
        borderRadius: AppTheme.radius,
        side: BorderSide(color: tone.withValues(alpha: .35)),
      ),
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (leading != null)
            leading!
          else if (icon != null)
            Icon(icon, size: 14, color: tone),
          if (leading != null || icon != null) const SizedBox(width: 5),
          Text(
            label,
            style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
          ),
        ],
      ),
    );
  }
}

/// Gravidade de um aviso — decide a cor, e só ela.
enum AppNoticeTone { info, warning, danger }

/// Faixa de aviso sobre o estado do aparelho.
///
/// Mesma receita de cor do [AppStatusBadge], em formato de linha inteira: é o
/// bloco por trás da fila offline, dos dados de cache, da versão nova do app e
/// do erro de login.
class AppNotice extends StatelessWidget {
  const AppNotice({
    super.key,
    required this.message,
    this.tone = AppNoticeTone.warning,
    this.icon,
    this.leading,
    this.trailing,
    this.actionLabel,
    this.onAction,
    this.onTap,
    this.selectable = false,
    this.footer,
  });

  final String message;
  final AppNoticeTone tone;
  final IconData? icon;

  /// Substitui o ícone (um progresso circular enquanto a fila esvazia).
  final Widget? leading;

  final Widget? trailing;
  final String? actionLabel;
  final VoidCallback? onAction;
  final VoidCallback? onTap;

  /// Deixa o texto ser copiado — só faz sentido em erro técnico, que o
  /// operador precisa mandar para o suporte.
  final bool selectable;

  /// Conteúdo abaixo da linha (uma barra de progresso, por exemplo).
  final Widget? footer;

  Color _color(BuildContext context) => switch (tone) {
    AppNoticeTone.info => Theme.of(context).colorScheme.primary,
    AppNoticeTone.warning => AppColors.warning,
    AppNoticeTone.danger => AppColors.danger,
  };

  @override
  Widget build(BuildContext context) {
    final color = _color(context);
    final style = TextStyle(
      fontSize: 13,
      fontWeight: FontWeight.w600,
      color: Theme.of(context).colorScheme.onSurface,
    );
    final box = Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: color.withValues(alpha: .12),
        borderRadius: AppTheme.radius,
        border: Border.all(color: color.withValues(alpha: .35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              leading ??
                  Icon(icon ?? Icons.info_outline, size: 18, color: color),
              const SizedBox(width: AppTheme.gap),
              Expanded(
                child: selectable
                    ? SelectableText(message, style: style)
                    : Text(message, style: style),
              ),
              if (actionLabel != null)
                TextButton(
                  onPressed: onAction,
                  style: TextButton.styleFrom(
                    foregroundColor: color,
                    minimumSize: Size.zero,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                  ),
                  child: Text(actionLabel!),
                ),
              ?trailing,
            ],
          ),
          if (footer != null) ...[
            const SizedBox(height: AppTheme.gapTight),
            footer!,
          ],
        ],
      ),
    );
    if (onTap == null) return box;
    return InkWell(onTap: onTap, borderRadius: AppTheme.radius, child: box);
  }
}
