part of 'order_detail_page.dart';

/// As três listas do atendimento, na ordem em que o garçom pensa: o que já
/// está na cozinha, o que ele acabou de escolher e ainda não mandou, e o que o
/// backend recusou. Antes era uma lista só, e "enviado" e "esperando" ficavam
/// indistinguíveis no meio do salão.
///
/// Vale igual para pedido e comanda — a anotação da comanda tem os MESMOS
/// campos do item de pedido, porque as duas são o mesmo consumo. É o que
/// permite uma tela só para os dois sem nenhum `if` aqui dentro.
class _ItemsList extends StatelessWidget {
  const _ItemsList({
    required this.presenter,
    required this.onVoid,
    required this.onDiscard,
  });

  final OrderDetailPresenter presenter;
  final ValueChanged<Map<String, dynamic>> onVoid;
  final ValueChanged<FailedMutation> onDiscard;

  @override
  Widget build(BuildContext context) {
    final sent = presenter.sentItems;
    final unsent = presenter.unsentItems;
    final drafts = presenter.draftItems;
    final queued = presenter.pendingAdds;
    final failures = presenter.failures;
    final toSend = unsent.length + queued.length + drafts.length;
    final busy = presenter.working;

    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
      children: [
        if (sent.isNotEmpty) ...[
          const AppSectionLabel(
            icon: Icons.soup_kitchen_outlined,
            label: 'Já na cozinha',
          ),
          for (final item in sent) _spaced(_tile(item)),
        ],
        if (toSend > 0) ...[
          AppSectionLabel(
            icon: Icons.schedule_outlined,
            label: 'A enviar ($toSend)',
          ),
          for (final item in unsent) _spaced(_tile(item)),
          for (final draft in drafts)
            _spaced(
              DraftItemTile(
                item: draft,
                onRemove: busy ? null : () => presenter.removeDraft(draft),
              ),
            ),
          for (final mutation in queued)
            _spaced(QueuedItemTile(mutation: mutation)),
        ],
        if (failures.isNotEmpty) ...[
          const AppSectionLabel(
            icon: Icons.error_outline,
            label: 'Não aceitos pelo servidor',
            color: AppColors.danger,
          ),
          for (final failure in failures)
            _spaced(
              FailedItemTile(
                failure: failure,
                onRetry: busy ? null : () => presenter.retryFailed(failure),
                onDiscard: busy ? null : () => onDiscard(failure),
              ),
            ),
        ],
      ],
    );
  }

  Widget _tile(Map<String, dynamic> item) {
    final voiding = presenter.voidingItemIds.contains('${item['id']}');
    return OrderItemTile(
      item: item,
      voiding: voiding,
      onVoid: (presenter.working || voiding) ? null : () => onVoid(item),
    );
  }

  static Widget _spaced(Widget child) =>
      Padding(padding: const EdgeInsets.only(bottom: 8), child: child);
}
