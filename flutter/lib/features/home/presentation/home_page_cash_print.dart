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
/// Mesmo caminho do recibo de venda e do DANFE: cupom montado aqui
/// ([CashPrintRenderer]), impressora master das preferências do terminal (ou
/// o diálogo de escolha quando não há master) e fila local pelo
/// [LocalDeviceAgent]. A operação de caixa já foi registrada quando qualquer
/// um destes roda — uma impressora fora do ar avisa, nunca desfaz.
mixin _CashPrintSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  LocalDeviceAgent get deviceAgent;
  Map<String, dynamic>? get selectedRestaurant;

  String get _cashOperatorName => widget.controller.session?.user.name ?? '';

  Future<void> _printCashOpening(Map<String, dynamic> session) =>
      _printCashDocument(
        title: 'Imprimir comprovante de abertura',
        summary:
            '${CashRegisterRepository.stationLabelOf(session)} · '
            '${_money(session['opening_amount'])}',
        content: CashPrintRenderer.opening(
          session: session,
          restaurant: selectedRestaurant,
          operatorName: _cashOperatorName,
        ),
        failureTitle: 'O comprovante de abertura não saiu na impressora',
      );

  Future<void> _printCashMovement(
    Map<String, dynamic> movement,
    Map<String, dynamic> session, {
    String authorizedBy = '',
    String managerReason = '',
  }) {
    final isWithdrawal = '${movement['movement_type']}' == 'withdrawal';
    return _printCashDocument(
      title: isWithdrawal
          ? 'Imprimir comprovante de sangria'
          : 'Imprimir comprovante de suprimento',
      summary:
          '${CashRegisterRepository.stationLabelOf(session)} · '
          '${_money(_number(movement['amount']).abs())}',
      content: CashPrintRenderer.movement(
        movement: movement,
        session: session,
        restaurant: selectedRestaurant,
        operatorName: _cashOperatorName,
        authorizedBy: authorizedBy,
        managerReason: managerReason,
      ),
      failureTitle: isWithdrawal
          ? 'O comprovante de sangria não saiu na impressora'
          : 'O comprovante de suprimento não saiu na impressora',
    );
  }

  Future<void> _printCashClosing(Map<String, dynamic> session) =>
      _printCashDocument(
        title: 'Imprimir relatório de fechamento',
        summary:
            '${CashRegisterRepository.stationLabelOf(session)} · '
            'esperado ${_money(session['expected_amount'])}',
        content: CashPrintRenderer.closing(
          session: session,
          restaurant: selectedRestaurant,
          operatorName: _cashOperatorName,
        ),
        failureTitle: 'O relatório de fechamento não saiu na impressora',
      );

  /// Escolhe a impressora como o recibo escolhe e manda para a fila local.
  Future<void> _printCashDocument({
    required String title,
    required String summary,
    required String content,
    required String failureTitle,
  }) async {
    try {
      final printers = await _list(
        '/printers/',
        query: {
          'restaurant': restaurantId,
          'is_active': true,
          'page_size': 100,
        },
      );
      if (!mounted) return;
      if (printers.isEmpty) {
        _error(
          const ApiException(
            'Nenhuma impressora ativa foi cadastrada para este restaurante.',
          ),
          title: failureTitle,
        );
        return;
      }
      // Se o caixa fixou uma impressora master, perguntar de novo aqui
      // aparece para ele como "o sistema ignorou a master".
      final master = widget.preferences.masterPrinterId;
      final hasMaster = printers.any((p) => '${p['id']}' == master);
      final printerId = hasMaster
          ? master
          : await showDialog<String>(
              context: context,
              builder: (_) => PrinterSelectionDialog(
                printers: printers,
                title: title,
                summary: summary,
                description:
                    'O comprovante sai na impressora escolhida, pela fila '
                    'local deste terminal.',
              ),
            );
      if (printerId == null || !mounted) return;
      final chosen = printers.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == printerId,
        orElse: () => null,
      );
      if (chosen == null) return;
      final printer = ReceiptPrinter(
        PrinterDevice.fromJson(chosen),
        runtime: deviceAgent.printing,
      );
      final result = await deviceAgent.submit(
        printer,
        printer.compose(content: content),
      );
      // Aceito na fila é silêncio (sai quando a impressora voltar); recusado
      // é aviso, porque nenhuma repetição resolve. Ver `_printReceiptLocally`.
      if (!result.accepted && mounted) {
        showAppToast(
          context,
          '$failureTitle. Confira a configuração da impressora.',
          severity: AppErrorSeverity.warning,
        );
      }
    } catch (error) {
      if (mounted) {
        _error(
          error,
          title: failureTitle,
          action: 'Confira a impressora selecionada e tente novamente.',
        );
      }
    }
  }
}
