import 'package:flutter/material.dart';

import 'app_error.dart';

/// Uma linha do histórico, construída somente quando entra no viewport.
class NotificationEntry extends StatelessWidget {
  const NotificationEntry({super.key, required this.item});

  final AppError item;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (cor, icone) = switch (item.severity) {
      AppErrorSeverity.failure => (scheme.error, Icons.error_outline),
      AppErrorSeverity.warning => (
        const Color(0xFF9A5B00),
        Icons.warning_amber_outlined,
      ),
      AppErrorSeverity.success => (
        const Color(0xFF1B7F3B),
        Icons.check_circle_outline,
      ),
      AppErrorSeverity.info => (scheme.primary, Icons.info_outline),
    };

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 11),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icone, color: cor, size: 19),
          const SizedBox(width: 11),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        item.title,
                        style: const TextStyle(
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    Text(
                      _horario(item.occurredAt),
                      style: TextStyle(
                        fontSize: 11,
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 2),
                Text(
                  item.message,
                  style: TextStyle(
                    fontSize: 12,
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  /// Hora e minuto bastam para o histórico de um turno.
  String _horario(DateTime quando) =>
      '${quando.hour.toString().padLeft(2, '0')}:'
      '${quando.minute.toString().padLeft(2, '0')}';
}
