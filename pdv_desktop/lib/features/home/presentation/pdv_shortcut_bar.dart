import 'package:flutter/material.dart';

class PdvShortcutBar extends StatelessWidget {
  const PdvShortcutBar({super.key, this.message});

  final String? message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      height: 30,
      padding: const EdgeInsets.symmetric(horizontal: 12),
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(top: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Row(
        children: [
          _keys('F2 ou /', 'Buscar'),
          _keys('Enter', 'Adicionar'),
          _keys('+ / −', 'Quantidade'),
          _keys('F4', 'Pagamento'),
          _keys('Esc', 'Voltar'),
          const Spacer(),
          if (message != null)
            Flexible(
              child: Text(
                message!,
                overflow: TextOverflow.ellipsis,
                textAlign: TextAlign.right,
                style: TextStyle(color: scheme.onSurfaceVariant, fontSize: 12),
              ),
            ),
        ],
      ),
    );
  }

  Widget _keys(String key, String action) => Padding(
    padding: const EdgeInsets.only(right: 18),
    child: Text.rich(
      TextSpan(
        children: [
          TextSpan(
            text: key,
            style: const TextStyle(fontWeight: FontWeight.w800),
          ),
          TextSpan(text: '  $action'),
        ],
      ),
      style: const TextStyle(fontSize: 12),
    ),
  );
}
