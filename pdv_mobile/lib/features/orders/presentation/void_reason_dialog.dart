import 'package:flutter/material.dart';

/// Os motivos de cancelamento, iguais aos do PDV desktop
/// (`ItemVoidReasonDialog.reasons`): o relatório de cancelamentos agrupa pelo
/// texto, e "cliente desistiu" escrito de cinco jeitos viraria cinco linhas.
const motivosDeCancelamento = [
  'Lançamento incorreto',
  'Cliente desistiu',
  'Item duplicado',
  'Produto indisponível',
  'Troca solicitada',
  'Outro',
];

/// Por que este item está sendo cancelado — um toque, não uma digitação.
///
/// O motivo é obrigatório: o cancelamento vira registro no caixa, e "sem
/// motivo" não explica nada a quem confere o fechamento no fim do turno.
/// "Outro" abre o campo para escrever.
Future<String?> askVoidReason(
  BuildContext context,
  Map<String, dynamic> item,
) => showDialog<String>(
  context: context,
  builder: (_) => _VoidReasonDialog(item: item),
);

class _VoidReasonDialog extends StatefulWidget {
  const _VoidReasonDialog({required this.item});

  final Map<String, dynamic> item;

  @override
  State<_VoidReasonDialog> createState() => _VoidReasonDialogState();
}

class _VoidReasonDialogState extends State<_VoidReasonDialog> {
  final _texto = TextEditingController();
  String? _escolhido;

  bool get _digitando => _escolhido == 'Outro';

  @override
  void dispose() {
    _texto.dispose();
    super.dispose();
  }

  void _confirmar() {
    final motivo = _digitando ? _texto.text.trim() : (_escolhido ?? '');
    if (motivo.isEmpty) return;
    Navigator.of(context).pop(motivo);
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text('Cancelar ${widget.item['product_name'] ?? 'item'}?'),
    content: SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              for (final motivo in motivosDeCancelamento)
                ChoiceChip(
                  label: Text(motivo),
                  selected: _escolhido == motivo,
                  onSelected: (_) => setState(() => _escolhido = motivo),
                ),
            ],
          ),
          if (_digitando) ...[
            const SizedBox(height: 12),
            TextField(
              controller: _texto,
              autofocus: true,
              decoration: const InputDecoration(labelText: 'Descreva o motivo'),
              onSubmitted: (_) => _confirmar(),
            ),
          ],
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: const Text('Voltar'),
      ),
      FilledButton(onPressed: _confirmar, child: const Text('Cancelar item')),
    ],
  );
}
