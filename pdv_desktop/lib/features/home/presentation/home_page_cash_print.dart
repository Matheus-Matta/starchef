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
        if (authorizedBy.trim().isNotEmpty) 'authorized_by': authorizedBy.trim(),
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

  /// Pede o texto ao servidor, escolhe a impressora como o recibo escolhe e
  /// manda para a fila local.
  Future<void> _printCashDocument({
    required Map<String, dynamic> session,
    required String document,
    required String title,
    required String summary,
    required String failureTitle,
    Map<String, String> extraQuery = const {},
  }) async {
    try {
      final rendered = await api.get(
        '/cash-register/${session['id']}/print-document/',
        query: {
          'document': document,
          'operator_name': _cashOperatorName,
          ...extraQuery,
        },
        accessToken: token,
      );
      final content = '${rendered['text_content'] ?? ''}';
      if (content.trim().isEmpty) {
        _error(
          const ApiException(
            'O servidor não devolveu o conteúdo do comprovante.',
          ),
          title: failureTitle,
        );
        return;
      }

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
      // ACEITO NA FILA é silêncio: a impressora não respondeu agora, mas o
      // cupom está guardado e sai sozinho quando ela voltar. Avisar a cada
      // tentativa encheria a tela de alertas sobre algo que o operador não tem
      // como acelerar — o estado fica na Fila de impressão, com o motivo.
      //
      // RECUSADO é outra coisa: nenhuma repetição resolve (impressora sem
      // endereço, configuração impossível) e só o operador pode agir.
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
