part of 'order_detail_presenter.dart';

/// O RECEBIMENTO — o aparelho operando como caixa secundário.
///
/// Fica separado porque é exatamente o que a COMANDA não tem. A mesma tela
/// atende pedido e comanda, e a fronteira entre as duas é esta: anotar e
/// mandar para a produção vale para os dois; cobrar é do caixa, que puxa as
/// anotações pendentes para um pedido.
///
/// Ver os dois assuntos separados no disco é o que impede alguém de alcançar
/// um recebimento de dentro do lançamento sem reparar no que está fazendo.
extension OrderDetailPayments on OrderDetailPresenter {
  /// Total já recebido, somando o que o backend confirmou.
  double get paid => _payments.fold<double>(
    0,
    (total, item) => total + amount(item['amount']),
  );

  double get remaining {
    final missing = amount(_order?['total']) - paid;
    return missing < 0 ? 0 : missing;
  }

  bool get awaitingPayment => '${_order?['status']}' == 'awaiting_payment';

  Future<String?> pay({
    required String methodId,
    required String methodName,
    required String cardSubtype,
    required String value,
    required String reference,
  }) => run(
    () => repository.pay(
      orderId: subjectId,
      paymentMethodId: methodId,
      amount: value,
      cardSubtype: cardSubtype,
      cashRegisterId: _cashRegisterId,
      reference: reference,
    ),
    'Recebimento registrado em $methodName.',
  );
  // ------------------------------------------------------------ recebimento

  /// Lê o que o recebimento precisa saber, sem prender a tela.
  ///
  /// Só depois de a conta fechar: enquanto o pedido está aberto o garçom está
  /// lançando item, e o que já foi recebido não muda nada na tela. Uma falha
  /// aqui não impede o lançamento — só esconde o botão de receber.
  Future<void> _loadPayments() async {
    if (!awaitingPayment) return;
    try {
      _payments = await repository.payments(subjectId);
      _notify();
    } catch (_) {
      // O backend não respondeu: o pedido continua utilizável para lançamento.
    }
  }

  /// Consulta o que só o backend sabe: quais formas de pagamento
  /// existem e qual sessão de caixa está aberta.
  ///
  /// Chamada no momento em que o operador vai receber, não a cada abertura de
  /// tela: eram três consultas ao backend por pedido — caro na rede do salão, e
  /// inútil enquanto o garçom está só lançando itens.
  Future<bool> loadPaymentOptions() async {
    if (_paymentMethods.isNotEmpty) return true;
    try {
      final methods = await repository.paymentMethods();
      final session = await repository.currentCashRegister();
      _paymentMethods = methods;
      _cashRegisterId = session == null ? null : '${session['id']}';
      _cashRegisterOpen = _cashRegisterId != null;
    } catch (_) {
      _paymentMethods = const [];
      _cashRegisterOpen = false;
    }
    _notify();
    return _paymentMethods.isNotEmpty;
  }
}
