import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

/// Confirma o estorno da venda agrupada — e diz o que ele vai levar junto.
///
/// O aviso é em texto, e não só um "tem certeza?". O operador precisa ler que
/// um cartão já reentregue vai ter o pedido do próximo cliente cancelado: é a
/// consequência que não se descobre clicando, e é a que gera reclamação no
/// balcão se ninguém a leu antes.
///
/// Devolve o motivo digitado, ou `null` quando o operador desiste. O motivo é
/// obrigatório porque ele é o que a auditoria tem para responder "por que esta
/// venda foi desfeita?".
Future<String?> showMergeRefundDialog(BuildContext context) =>
    showDialog<String>(
      context: context,
      builder: (_) => const _MergeRefundDialog(),
    );

class _MergeRefundDialog extends StatefulWidget {
  const _MergeRefundDialog();

  @override
  State<_MergeRefundDialog> createState() => _MergeRefundDialogState();
}

class _MergeRefundDialogState extends State<_MergeRefundDialog> {
  // O diálogo é DONO do controlador e o descarta no `dispose` do próprio
  // `State`, que só roda depois que a rota termina de sair — criá-lo fora e
  // descartá-lo logo após o `await` descartaria cedo demais.
  final _motivo = TextEditingController();

  @override
  void dispose() {
    _motivo.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AppDialog(
      maxWidth: 560,
      destructive: true,
      title: const Text('Estornar a venda agrupada'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: scheme.errorContainer,
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              'Isto cancela o pagamento, devolve o estoque, cancela a nota '
              'fiscal e ESVAZIA todas as comandas da conta.\n\n'
              'Se algum cartão já foi reentregue a outro cliente, o pedido '
              'dele também será cancelado.',
              style: TextStyle(color: scheme.onErrorContainer),
            ),
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _motivo,
            autofocus: true,
            maxLines: 2,
            decoration: const InputDecoration(
              labelText: 'Motivo do estorno',
              helperText: 'Obrigatório — é o que a auditoria vai mostrar depois.',
            ),
            onSubmitted: (valor) => _confirmar(valor),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Voltar'),
        ),
        ValueListenableBuilder(
          valueListenable: _motivo,
          builder: (context, valor, _) => FilledButton(
            // Sem motivo o botão não acende: recusar depois do clique ensina o
            // operador a digitar qualquer coisa para passar.
            onPressed: valor.text.trim().isEmpty
                ? null
                : () => _confirmar(valor.text),
            child: const Text('Estornar'),
          ),
        ),
      ],
    );
  }

  void _confirmar(String valor) {
    final motivo = valor.trim();
    if (motivo.isEmpty) return;
    Navigator.of(context).pop(motivo);
  }
}
