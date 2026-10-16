import 'package:flutter/material.dart';

import '../../customers/presentation/customers_page.dart';
import '../data/orders_repository.dart';
import 'comandas_presenter.dart';
import 'order_detail_page.dart';

/// Para onde a grade da tela inicial LEVA o garçom.
///
/// Fica separado da página porque são dois assuntos: a página desenha a grade
/// e seus estados; isto aqui decide o que abrir.
mixin OrdersPageNavigation<T extends StatefulWidget> on State<T> {
  // ── fornecido pela página ───────────────────────────────────────────────
  OrdersRepository get repository;
  ComandasPresenter get presenter;

  /// O cartão tocado, com o CARDÁPIO JÁ ABERTO.
  ///
  /// Abrir a comanda e depois tocar em "Adicionar item" era um toque a mais em
  /// todo lançamento do turno. A comanda não é um pedido: anota, e o pedido só
  /// nasce no caixa.
  Future<void> openCommand(Map<String, dynamic> command) async {
    final id = '${command['id']}';
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => OrderDetailPage(
          repository: repository,
          subject: OrderSubject.command(id),
          abrirCardapio: true,
        ),
      ),
    );
    // Relê só este cartão: a rodada pode ter acabado de subir.
    if (mounted) await presenter.atualizar(id);
  }

  /// O cadastro de clientes, pelo menu da conta.
  Future<void> openCustomers() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => CustomersPage(repository: repository),
      ),
    );
  }
}
