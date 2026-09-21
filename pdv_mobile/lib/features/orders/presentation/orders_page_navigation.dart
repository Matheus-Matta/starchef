import 'package:flutter/material.dart';

import '../data/orders_repository.dart';
import 'command_detail_page.dart';
import 'new_order_flow.dart';
import 'order_detail_page.dart';
import 'orders_presenter.dart';

/// Para onde a lista de pedidos LEVA o garçom.
///
/// Fica separado da página porque são dois assuntos: a página desenha a lista e
/// seus estados; isto aqui decide qual tela abrir. E a decisão deixou de ser
/// óbvia — o cartão e o pedido são coisas diferentes agora, e o fluxo de
/// abertura pode devolver qualquer um dos dois.
mixin OrdersPageNavigation<T extends StatefulWidget> on State<T> {
  // ── fornecido pela página ───────────────────────────────────────────────
  OrdersRepository get repository;
  OrdersPresenter get presenter;

  Future<void> openOrder(Map<String, dynamic> order) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OrderDetailPage(
          repository: repository,
          orderId: '${order['id']}',
        ),
      ),
    );
    // Relê ao voltar: o pedido pode ter mudado, e a lista mostra estado.
    if (mounted) await presenter.load();
  }

  /// O cartão aberto. **Não é um pedido**: a comanda anota, e o pedido só
  /// nasce no caixa com as anotações pendentes.
  Future<void> openCommand(Map<String, dynamic> command) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            CommandDetailPage(repository: repository, command: command),
      ),
    );
    if (mounted) await presenter.load();
  }

  /// Abre o que o fluxo devolveu — cartão ou pedido.
  ///
  /// O fluxo marca o que é: sem isso a tela teria de adivinhar pelo formato do
  /// mapa, e adivinhar erraria no dia em que um dos dois ganhasse um campo.
  Future<void> openNewFlowResult() async {
    final resultado = await startNewOrder(context, repository);
    if (resultado == null || !mounted) return;
    if (resultado['_kind'] == 'command') {
      await openCommand(resultado);
      return;
    }
    await openOrder(resultado);
  }
}
