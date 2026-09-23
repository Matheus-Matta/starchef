import 'package:flutter/material.dart';

import '../update/pdv_update_service.dart';

class PdvVersionIndicator extends StatelessWidget {
  const PdvVersionIndicator({
    super.key,
    required this.status,
    this.onPressed,
    this.showProductName = false,
    this.showState = true,
  });

  final PdvUpdateStatus? status;
  final VoidCallback? onPressed;
  final bool showProductName;
  final bool showState;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final installed = status?.installed?.version;
    final (icon, tone, state, tooltip) = switch (status?.phase) {
      PdvUpdatePhase.checking => (
        Icons.sync_rounded,
        scheme.onSurfaceVariant,
        'Verificando',
        'Verificando se existe uma versão nova',
      ),
      PdvUpdatePhase.upToDate => (
        Icons.check_circle,
        const Color(0xFF16A34A),
        'Atualizado',
        'O aplicativo está atualizado',
      ),
      PdvUpdatePhase.updateAvailable => (
        Icons.system_update_alt,
        const Color(0xFFDC2626),
        'Atualização disponível',
        'Nova versão: v${status?.latestVersion}',
      ),
      PdvUpdatePhase.unavailable => (
        Icons.help_outline,
        scheme.onSurfaceVariant,
        'Não verificado',
        status?.detail ?? 'Não foi possível verificar atualizações',
      ),
      null => (
        Icons.sync_rounded,
        scheme.onSurfaceVariant,
        'Verificando',
        'Verificando a versão instalada',
      ),
    };
    final parts = <String>[
      if (showProductName) 'STARCHEF',
      installed == null ? 'versão…' : 'v$installed',
      if (showState) state,
    ];
    final label = parts.join(' · ');
    final content = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 16, color: tone),
        const SizedBox(width: 5),
        Flexible(
          child: Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              color: tone,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
        ),
      ],
    );

    return Tooltip(
      message: tooltip,
      child: onPressed == null
          ? content
          : InkWell(
              borderRadius: BorderRadius.circular(6),
              onTap: onPressed,
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: content,
              ),
            ),
    );
  }
}
