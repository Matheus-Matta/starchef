// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O caminho de um comprovante de caixa até o papel.
///
/// Está separado de `_CashPrintSection` porque são duas perguntas diferentes:
/// lá se decide QUAL comprovante existe (abertura, sangria, suprimento,
/// fechamento), aqui se resolve COMO qualquer um deles chega à impressora —
/// pedir o texto ao servidor, escolher o equipamento e entregar à fila local.
mixin _CashPrintDelivery on _HomePageShared {
  LocalDeviceAgent get deviceAgent;

  String get _cashOperatorName;

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
        // Todo documento daqui existe porque alguém vai pôr a mão no
        // dinheiro: abertura conta o fundo de troco, sangria tira, suprimento
        // põe e o fechamento confere. A gaveta abre junto com o comprovante,
        // e não em um segundo gesto.
        printer.compose(content: content, openCashDrawer: true),
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
          severity: AppErrorSeverity.failure,
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
