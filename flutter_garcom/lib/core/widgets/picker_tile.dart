import 'package:flutter/material.dart';

import '../theme/app_theme.dart';

/// Cartão padrão dos itens escolhíveis de uma folha (comanda, produto).
class PickerTile extends StatelessWidget {
  const PickerTile({
    super.key,
    required this.title,
    required this.onTap,
    this.subtitle,
    this.trailing,
    this.leading,
    this.enabled = true,
  });

  final String title;
  final String? subtitle;
  final Widget? trailing;
  final Widget? leading;
  final VoidCallback onTap;
  final bool enabled;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Material(
      color: scheme.surface,
      borderRadius: AppTheme.radius,
      child: InkWell(
        onTap: enabled ? onTap : null,
        borderRadius: AppTheme.radius,
        child: Container(
          constraints: const BoxConstraints(minHeight: AppTheme.controlHeight),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
          decoration: BoxDecoration(
            borderRadius: AppTheme.radius,
            border: Border.all(color: scheme.outlineVariant),
          ),
          child: Opacity(
            opacity: enabled ? 1 : .5,
            child: Row(
              children: [
                if (leading != null) ...[leading!, const SizedBox(width: 12)],
                Expanded(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 15,
                        ),
                      ),
                      if (subtitle != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          subtitle!,
                          style: TextStyle(
                            fontSize: 12,
                            color: scheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                ?trailing,
              ],
            ),
          ),
        ),
      ),
    );
  }
}
