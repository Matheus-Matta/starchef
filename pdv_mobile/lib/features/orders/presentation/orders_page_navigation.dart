import 'package:flutter/material.dart';

import '../data/orders_repository.dart';
import 'new_order_flow.dart';
import 'order_detail_page.dart';
import 'orders_presenter.dart';

/// Para onde a lista da tela inicial LEVA o garçom.
///
/// Fica separado da página porque são dois assuntos: a página desenha a lista
/// e seus estados; isto aqui decide o que abrir. A tela de destino é a mesma
/// para pedido e comanda — o que muda é o [OrderSubject] que ela recebe.
mixin OrdersPageNavigation<T extends StatefulWidget> on State<T> {
  // ── fornecido pela página ───────────────────────────────────────────────
  OrdersRepository get repository;
  OrdersPresenter get presenter;

  Future<void> openOrder(Map<String, dynamic> order) =>
      _open(OrderSubject.order('${order['id']}'));

  /// O cartão aberto. **Não é um pedido**: a comanda anota, e o pedido só
  /// nasce no caixa com as anotações pendentes. A TELA é a mesma; o que ela
  /// não oferece para a comanda é receber.
  Future<void> openCommand(Map<String, dynamic> command) =>
      _open(OrderSubject.command('${command['id']}'));

  Future<void> _open(OrderSubject subject) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            OrderDetailPage(repository: repository, subject: subject),
      ),
    );
    // Relê ao voltar: o atendimento pode ter mudado, e a lista mostra estado.
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
