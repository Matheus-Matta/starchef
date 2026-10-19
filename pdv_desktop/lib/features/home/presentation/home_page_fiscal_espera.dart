// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O DANFE depois da venda: a pergunta, a espera pela SEFAZ e a nota achada
/// pelo pedido. Tudo em segundo plano — o caixa já está no próximo cliente.
///
/// Saiu de `_FiscalSection` (os métodos de espera foram MOVIDOS, não
/// reescritos), que segue com a emissão e a impressão.
mixin _FiscalEsperaSection on _HomePageShared {
  // ── fornecido por `_FiscalSection` e `_HomePageState` ───────────────────
  Set<String> get watchedFiscalInvoices;
  Future<void> _printDanfe({
    required String invoiceId,
    required String summary,
    bool automatic,
    Future<String?>? salePrinter,
  });
  void _showFiscalStateToast(
    Map<String, dynamic> invoice, {
    required bool silent,
  });

  /// Espera a SEFAZ autorizar e manda o DANFE para a impressora sozinho.
  ///
  /// Online, a emissão quase nunca volta autorizada: o provedor ACEITA a nota
  /// e a SEFAZ responde um instante depois. O "Concluir pedido" terminava
  /// então com um aviso e nenhum cupom fiscal — o operador tinha de voltar no
  /// pedido e mandar imprimir na mão, para uma nota que já estava autorizada
  /// havia dois segundos.
  ///
  /// Consulta em segundo plano, com espera crescente: o caixa já pode começar
  /// a próxima venda. Se a autorização não chegar na janela, nada se perde —
  /// a nota continua na esteira normal (webhook e consulta periódica) e o
  /// cupom sai pela reimpressão no histórico do pedido.
  void _watchFiscalAuthorization(
    Map<String, dynamic> invoice, {
    required String summary,
    Future<String?>? salePrinter,
    Future<bool>? printDecision,
  }) {
    final invoiceId = '${invoice['id'] ?? ''}';
    if (!danfeOnTheWay(invoice)) return;
    // Um segundo vigia sobre a mesma nota mandaria o DANFE para a impressora
    // de novo — e a segunda via seria um cupom NOVO, porque o trabalho da
    // primeira já teria saído.
    if (!watchedFiscalInvoices.add(invoiceId)) return;
    unawaited(
      _pollFiscalAuthorization(
        invoiceId: invoiceId,
        summary: summary,
        salePrinter: salePrinter,
        printDecision: printDecision,
      ),
    );
  }

  /// Pergunta se imprime o DANFE desta venda. `false` = não imprimir.
  ///
  /// Espera a escolha de impressora da venda terminar: dois modais empilhados
  /// disputariam o mesmo Enter. Sem impressora escolhida não há o que
  /// perguntar — o DANFE não sairia de qualquer jeito.
  Future<bool> _askPrintDanfe(
    String summary,
    Future<String?>? salePrinter,
  ) async {
    if (salePrinter != null && await salePrinter == null) return false;
    if (!mounted) return false;
    final wants = await DanfePrintQuestionDialog.ask(context, summary: summary);
    AppLogger.instance.info(
      'danfe_pergunta_respondida',
      data: {'resumo': summary, 'imprimir': wants},
    );
    return wants;
  }

  Future<void> _pollFiscalAuthorization({
    required String invoiceId,
    required String summary,
    Future<String?>? salePrinter,
    Future<bool>? printDecision,
  }) async {
    try {
      await _pollFiscalAuthorizationNow(
        invoiceId: invoiceId,
        summary: summary,
        salePrinter: salePrinter,
        printDecision: printDecision,
      );
    } finally {
      watchedFiscalInvoices.remove(invoiceId);
    }
  }

  Future<void> _pollFiscalAuthorizationNow({
    required String invoiceId,
    required String summary,
    Future<String?>? salePrinter,
    Future<bool>? printDecision,
  }) async {
    const backoff = [
      Duration(milliseconds: 1200),
      Duration(seconds: 2),
      Duration(seconds: 3),
      Duration(seconds: 4),
      Duration(seconds: 5),
    ];
    for (final wait in backoff) {
      await Future<void>.delayed(wait);
      if (!mounted) return;
      final Map<String, dynamic> current;
      try {
        current = await api.post(
          '/invoices/$invoiceId/refresh-status/',
          // "Estou esperando esta autorizacao para imprimir." Sem avisar, o
          // cupom que esta consulta cria entra no laco automatico do agente
          // local e o cliente recebe DOIS DANFEs: o do agente e o que este
          // terminal manda em seguida.
          body: const {'manual_print': true},
          accessToken: token,
        );
      } catch (_) {
        // Um tropeço de rede não abandona a nota: a próxima volta tenta de
        // novo. Desistir aqui era barato quando o servidor criava o cupom
        // sozinho — não é mais: numa venda de terminal (`terminal_prints`)
        // ninguém mais imprime este DANFE se esta espera desistir.
        continue;
      }
      if (!mounted) return;
      AppLogger.instance.info(
        'fiscal_consulta_autorizacao',
        data: {
          'nota': invoiceId,
          'printable': current['printable'],
          'fiscal_state': current['fiscal_state'],
        },
      );
      if (current['printable'] == true) {
        // O operador disse não no modal: a nota segue autorizada, só o
        // papel não sai.
        if (printDecision != null && !await printDecision) return;
        if (!mounted) return;
        await _printDanfe(
          invoiceId: invoiceId,
          summary: summary,
          automatic: true,
          salePrinter: salePrinter,
        );
        return;
      }
      final state = '${current['fiscal_state'] ?? ''}';
      if (state == 'rejected' || state == 'configuration_error') {
        // Agora sim interrompe: isto não se resolve esperando.
        _showFiscalStateToast(current, silent: false);
        return;
      }
    }
    // A janela acabou e a autorização não chegou. O operador precisa saber:
    // numa venda de terminal o servidor não cria cupom automático, então este
    // DANFE só sai se alguém mandar imprimir pelo histórico do pedido.
    // Quem respondeu "não" no modal não precisa do aviso.
    if (printDecision != null && !await printDecision) return;
    if (!mounted) return;
    showAppToast(
      context,
      'A SEFAZ ainda não autorizou a NFC-e desta venda. Quando autorizar, '
      'imprima o DANFE pelo pedido em Pedidos.',
      severity: AppErrorSeverity.warning,
    );
  }
}
