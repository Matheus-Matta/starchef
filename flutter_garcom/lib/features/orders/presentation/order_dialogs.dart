import 'package:flutter/material.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/relay/pending_mutation.dart';
import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/app_toast.dart';
import 'order_detail_presenter.dart';
import 'order_formatters.dart';
import 'table_picker_sheet.dart';

/// As perguntas que a tela do pedido faz antes de gravar alguma coisa.
///
/// Ficam fora da página porque são conversas curtas e independentes: cada uma
/// abre, pergunta uma coisa e devolve a resposta. Misturadas ao `State` elas
/// engordavam a tela e escondiam o fluxo principal — lançar item e enviar.

/// Por que este item está sendo cancelado.
///
/// O motivo é obrigatório: o cancelamento vira registro no caixa, e "sem
/// motivo" não explica nada a quem confere o fechamento no fim do turno.
Future<String?> askVoidReason(BuildContext context, Map<String, dynamic> item) {
  final controller = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: Text('Cancelar ${item['product_name'] ?? 'item'}?'),
      content: TextField(
        controller: controller,
        autofocus: true,
        decoration: const InputDecoration(
          labelText: 'Motivo',
          hintText: 'Ex.: cliente desistiu',
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Voltar'),
        ),
        FilledButton(
          onPressed: () {
            final reason = controller.text.trim();
            if (reason.isEmpty) return;
            Navigator.of(context).pop(reason);
          },
          child: const Text('Cancelar item'),
        ),
      ],
    ),
  );
}

/// Apagar deste aparelho uma operação que o caixa recusou.
Future<bool> confirmDiscardFailed(
  BuildContext context,
  FailedMutation failure,
) async {
  final confirmed = await showDialog<bool>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Remover este item?'),
      content: Text(
        '"${failure.mutation.summary}" não foi aceito pelo caixa e será '
        'apagado deste aparelho. O pedido não muda — o item simplesmente '
        'nunca entrou nele.',
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context, false),
          child: const Text('Manter'),
        ),
        FilledButton(
          onPressed: () => Navigator.pop(context, true),
          child: const Text('Remover'),
        ),
      ],
    ),
  );
  return confirmed ?? false;
}

/// Vincular, trocar ou desvincular a mesa de uma comanda.
///
/// A mesa é um detalhe do atendimento, não a identidade do pedido: o cliente
/// pode chegar em pé, sentar depois e trocar de lugar. Por isso ela se
/// gerencia aqui dentro, e não na hora de abrir o pedido.
///
/// Devolve o recado a mostrar ao garçom, ou `null` se ele desistiu.
/// [skipAsk] entra direto na escolha da mesa, sem perguntar o que fazer.
/// É o caminho da sugestão automática: o garçom já respondeu "quero vincular"
/// ao aceitar a sugestão, e repetir a pergunta seria um toque a mais para a
/// mesma decisão.
Future<String?> manageOrderTable(
  BuildContext context,
  OrderDetailPresenter presenter, {
  bool skipAsk = false,
}) async {
  final order = presenter.order;
  if (order == null) return null;
  final commandId = fieldText(order['command']);
  if (commandId.isEmpty) return null;
  final hasTable = fieldText(order['table']).isNotEmpty;

  if (!skipAsk) {
    final action = await _askTableAction(context, hasTable: hasTable);
    if (action == null || !context.mounted) return null;
    if (action == _TableAction.unlink) return presenter.unlinkTable(commandId);
  }
  final List<Map<String, dynamic>> tables;
  try {
    tables = await presenter.repository.tables();
  } catch (error) {
    return describeFailure(error);
  }
  if (!context.mounted) return null;
  final table = await showTablePicker(
    context,
    tables,
    commandLabel: orderTitle(order),
  );
  if (table == null) return null;
  return presenter.linkTable(
    commandId,
    table,
    success: hasTable
        ? 'Comanda transferida de mesa.'
        : 'Comanda vinculada à mesa.',
  );
}

/// Este pedido merece a sugestão de mesa ao ser aberto?
///
/// Só comanda tem mesa para vincular (é o contrato de [manageOrderTable]), e
/// só faz sentido sugerir para quem ainda não tem uma.
bool shouldSuggestTable(Map<String, dynamic>? order) {
  if (order == null) return false;
  if (fieldText(order['command']).isEmpty) return false;
  return fieldText(order['table']).isEmpty;
}

/// "Este pedido está sem mesa. Quer vincular uma agora?"
///
/// Sugestão, não bloqueio: o cliente pode estar em pé, e o pedido segue
/// utilizável de qualquer forma. O que não pode é o garçom entrar no pedido,
/// não ser lembrado, e a comanda passar o atendimento inteiro sem ninguém
/// saber para onde levar o que foi pedido.
Future<bool?> confirmLinkTableSuggestion(BuildContext context) =>
    showAppSheet<bool>(
      context,
      builder: (context) => Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const AppSheetHeader(title: 'Pedido sem mesa'),
          const Padding(
            padding: EdgeInsets.symmetric(horizontal: 16),
            child: Text('Deseja vincular uma mesa a este pedido?'),
          ),
          const SizedBox(height: 12),
          AppSheetOption(
            icon: Icons.table_restaurant_outlined,
            label: 'Selecionar mesa',
            onTap: () => Navigator.pop(context, true),
          ),
          AppSheetOption(
            icon: Icons.schedule_outlined,
            label: 'Agora não',
            onTap: () => Navigator.pop(context, false),
          ),
          const SizedBox(height: 12),
        ],
      ),
    );

enum _TableAction { link, unlink }

Future<_TableAction?> _askTableAction(
  BuildContext context, {
  required bool hasTable,
}) => showAppSheet<_TableAction>(
  context,
  builder: (context) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [
      const AppSheetHeader(title: 'Mesa da comanda'),
      AppSheetOption(
        icon: Icons.table_restaurant_outlined,
        label: hasTable ? 'Trocar de mesa' : 'Vincular a uma mesa',
        onTap: () => Navigator.pop(context, _TableAction.link),
      ),
      if (hasTable)
        AppSheetOption(
          icon: Icons.link_off_outlined,
          label: 'Desvincular da mesa',
          onTap: () => Navigator.pop(context, _TableAction.unlink),
        ),
      const SizedBox(height: 12),
    ],
  ),
);

/// Mostra o recado de uma operação, quando ela produziu um.
void reportOutcome(BuildContext context, String? message) {
  if (message != null && context.mounted) showToast(context, message);
}
