// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Comprovantes do caixa no papel: abertura, sangria, suprimento e o
/// relatório de fechamento.
///
/// Mesmo caminho do recibo de venda e do DANFE: o SERVIDOR monta o texto
/// (`/cash-register/{id}/print-document/`), o terminal escolhe a impressora e
/// a fila local põe no papel. O relatório de fechamento é o documento que o
/// operador assina — tê-lo montado em dois lugares faria a primeira mudança de
/// regra aparecer como divergência no papel assinado.
///
/// A operação de caixa já foi registrada quando qualquer um destes roda — uma
/// impressora fora do ar avisa, nunca desfaz.
mixin _CashPrintSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;
  Map<String, dynamic>? get selectedRestaurant;

  String get _cashOperatorName => widget.controller.session?.user.name ?? '';

  Future<void> _printCashOpening(Map<String, dynamic> session) =>
      _printCashDocument(
        session: session,
        document: 'opening',
        title: 'Imprimir comprovante de abertura',
        summary:
            '${cashStationLabelOf(session)} · '
            '${_money(session['opening_amount'])}',
        failureTitle: 'O comprovante de abertura não saiu na impressora',
      );

  Future<void> _printCashOpeningDivergence(Map<String, dynamic> session) =>
      _printCashDocument(
        session: session,
        document: 'opening_divergence',
        title: 'Imprimir divergência autorizada da abertura',
        summary:
            '${cashStationLabelOf(session)} · '
            'diferença ${_money(session['difference_amount'])}',
        failureTitle:
            'O comprovante da divergência de abertura não saiu na impressora',
      );

  Future<void> _printCashMovement(
    Map<String, dynamic> movement,
    Map<String, dynamic> session, {
    String authorizedBy = '',
    String managerReason = '',
  }) {
    final isWithdrawal = '${movement['movement_type']}' == 'withdrawal';
    return _printCashDocument(
      session: session,
      document: isWithdrawal ? 'withdrawal' : 'supply',
      extraQuery: {
        'movement': '${movement['id']}',
        if (authorizedBy.trim().isNotEmpty)
          'authorized_by': authorizedBy.trim(),
        if (managerReason.trim().isNotEmpty)
          'manager_reason': managerReason.trim(),
      },
      title: isWithdrawal
          ? 'Imprimir comprovante de sangria'
          : 'Imprimir comprovante de suprimento',
      summary:
          '${cashStationLabelOf(session)} · '
          '${_money(_number(movement['amount']).abs())}',
      failureTitle: isWithdrawal
          ? 'O comprovante de sangria não saiu na impressora'
          : 'O comprovante de suprimento não saiu na impressora',
    );
  }

  Future<void> _printCashClosing(Map<String, dynamic> session) =>
      _printCashDocument(
        session: session,
        document: 'closing',
        title: 'Imprimir relatório de fechamento',
        summary:
            '${cashStationLabelOf(session)} · '
            'esperado ${_money(session['expected_amount'])}',
        failureTitle: 'O relatório de fechamento não saiu na impressora',
      );

  /// Põe um comprovante de caixa no papel — implementado em
  /// `home_page_cash_print_send.dart`.
  Future<void> _printCashDocument({
    required Map<String, dynamic> session,
    required String document,
    required String title,
    required String summary,
    required String failureTitle,
    Map<String, String> extraQuery,
  });
}
