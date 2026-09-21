import 'package:flutter/material.dart';

import '../../../core/widgets/app_dialog.dart';

/// Cancelar uma anotação da comanda pede MOTIVO e deixa registro.
///
/// E avisa antes quando o item já foi para a produção: sai um cupom de
/// cancelamento na impressora do setor, e o operador descobriria isso pelo
/// barulho da impressora.
///
/// Devolve o motivo, ou `null` quando o operador desistiu. Motivo em branco
/// conta como desistência: o servidor recusa mesmo, e gastar uma ida à rede
/// para ouvir isso seria pior.
Future<String?> showCommandVoidDialog(
  BuildContext context, {
  required Map<String, dynamic> item,
}) async {
  final motivo = await showDialog<String>(
    context: context,
    builder: (_) => _CommandVoidDialog(item: item),
  );
  return (motivo == null || motivo.isEmpty) ? null : motivo;
}

/// O diálogo é dono do controlador e o descarta no `dispose` do próprio
/// `State` — que só roda depois que a rota termina de sair.
///
/// Criá-lo na função acima e descartá-lo logo após o `await` descarta cedo
/// demais: o `await showDialog` volta com a animação de saída ainda rodando, e
/// o campo continua sendo desenhado com um controlador já morto.
class _CommandVoidDialog extends StatefulWidget {
  const _CommandVoidDialog({required this.item});

  final Map<String, dynamic> item;

  @override
  State<_CommandVoidDialog> createState() => _CommandVoidDialogState();
}

class _CommandVoidDialogState extends State<_CommandVoidDialog> {
  final _motivo = TextEditingController();

  @override
  void dispose() {
    _motivo.dispose();
    super.dispose();
  }

  bool get _naCozinha => '${widget.item['status'] ?? ''}' != 'pending';

  void _confirmar() => Navigator.pop(context, _motivo.text.trim());

  @override
  Widget build(BuildContext context) {
    return AppDialog(
      maxWidth: 460,
      title: Text(_naCozinha ? 'Cancelar item em produção' : 'Remover item'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            '${widget.item['product_name'] ?? 'Item da comanda'}',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
          if (_naCozinha)
            const Padding(
              padding: EdgeInsets.only(top: 8),
              child: Text(
                'Este item já foi enviado para a cozinha. Uma nota de '
                'cancelamento será impressa no setor que o recebeu.',
              ),
            ),
          const SizedBox(height: 12),
          TextField(
            controller: _motivo,
            autofocus: true,
            decoration: const InputDecoration(labelText: 'Motivo'),
            onSubmitted: (_) => _confirmar(),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Voltar'),
        ),
        FilledButton(
          onPressed: _confirmar,
          child: Text(
            _naCozinha ? 'Cancelar e avisar cozinha' : 'Remover item',
          ),
        ),
      ],
    );
  }
}
