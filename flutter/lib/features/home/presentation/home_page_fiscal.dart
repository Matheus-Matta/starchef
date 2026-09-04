part of 'home_page.dart';

/// Emissão da NFC-e e impressão do DANFE.
///
/// Vive num `part` da mesma biblioteca porque o código continua sendo o mesmo
/// — os métodos foram MOVIDOS, não reescritos — e precisa enxergar os nomes
/// privados da tela. O que a seção usa de fora está declarado abaixo como
/// membro abstrato: é o contrato explícito dela com o resto do PDV, e ele
/// falha na compilação se alguém mudar um lado sem o outro.
mixin _FiscalSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get selectedCustomer;
  LocalDeviceAgent get deviceAgent;
  Set<String> get watchedFiscalInvoices;
  bool get emittingInvoice;
  set emittingInvoice(bool value);

  /// Operação fiscal separada da venda (§16): emite a NFC-e
  /// (POST /invoices/emit) e, se conseguir, imprime o DANFE
  /// (POST /invoices/{id}/print).
  ///
  /// A venda NÃO depende disto. Sem conexão, a emissão entra na fila fiscal e
  /// o documento fica `PENDING` enquanto o pedido já está pago — antes, a
  /// mesma situação devolvia um erro no meio do recebimento, como se a venda
  /// tivesse falhado.
  ///
  /// O DANFE só é impresso para nota AUTORIZADA. Uma nota pendente tem chave
  /// montada localmente, que a consulta no portal da SEFAZ não encontra:
  /// imprimi-la entregaria ao cliente um cupom que não corresponde a documento
  /// fiscal nenhum.
  ///
  /// [silentIfUnconfigured] evita um alerta em toda venda de restaurantes que
  /// ainda não configuraram Fiscal > Configuração — chamado automaticamente
  /// após cada pagamento, isso spammaria caixas que nem usam NFC-e ainda.
  /// Qualquer outra falha (SEFAZ fora do ar, certificado vencido) continua
  /// visível, porque nesse caso o DANFE realmente não saiu para o cliente.
  Future<void> _emitFiscalInvoice(
    Map<String, dynamic> order, {
    bool silentIfUnconfigured = false,
  }) async {
    if (emittingInvoice) return;
    setState(() => emittingInvoice = true);
    try {
      // NÃO passa por `_work`: aquela trava serve para o operador não disparar
      // duas operações de venda ao mesmo tempo, e DESISTE quando já há uma em
      // curso (`if (busy) return null`). A emissão é efeito de uma venda que
      // já terminou — engolida pela trava, a nota simplesmente não era pedida:
      // sem erro, sem fila fiscal, sem cupom.
      Map<String, dynamic>? invoice;
      try {
        invoice = await api.post(
          '/invoices/emit/',
          body: {
            'order': order['id'],
            if (selectedCustomer?['document'] != null)
              'cpf': selectedCustomer!['document'],
            if (selectedCustomer?['name'] != null)
              'cpf_name': selectedCustomer!['name'],
          },
          accessToken: token,
        );
      } catch (error) {
        AppLogger.instance.warning(
          'fiscal_emit_recusado',
          data: {'pedido': '${order['id']}', 'causa': '$error'},
        );
        if (!mounted) return;
        // "Restaurante não emite NFC-e" é a única recusa que pode ser calada
        // numa emissão automática — o resto o operador precisa ver.
        if (!silentIfUnconfigured ||
            !'$error'.toLowerCase().contains('configuracao fiscal')) {
          _error(error, title: 'Não foi possível emitir a NFC-e');
        }
        return;
      }
      if (!mounted) return;

      AppLogger.instance.info(
        'fiscal_emit_resposta',
        data: {
          'pedido': '${order['id']}',
          'fiscal_pending': invoice['_fiscal_pending'],
          'emitted': invoice['emitted'],
          'printable': invoice['printable'],
          'fiscal_state': invoice['fiscal_state'],
        },
      );

      // Emissão adiada (§16): a venda já está concluída e o documento entrou
      // na fila fiscal. Não há DANFE para imprimir agora — o cupom fiscal sai
      // quando a nota for autorizada.
      if (invoice['_fiscal_pending'] == true) {
        final issues = (invoice['_fiscal_issues'] as List? ?? const [])
            .map((issue) => '$issue')
            .toList();
        // Toda emissao passa pela fila (§16), mesmo com internet — e o que
        // garante que uma queda no meio do caminho nao perca o documento.
        // Mas esperar o ciclo de 30 segundos para o cupom fiscal sair
        // deixaria o cliente parado no balcao: com conexao, entrega a nota
        // agora e imprime em seguida, no mesmo gesto do recibo. Algumas
        // insistencias curtas cobrem uma entrega que estava só um instante
        // atrás da nossa (outro ciclo de sincronização em voo, um ping que
        // falhou uma vez) sem prender o caixa por muito tempo.
        //
        // PENDÊNCIA NO RETRATO LOCAL AVISA, MAS NÃO VETA. Quem decide se a
        // nota passa é o servidor, que enxerga a venda inteira; aqui só existe
        // o que este terminal guardou. O veto matou uma NFC-e cujo recebimento
        // EXISTIA — ele tinha acabado de subir, e a versão do pedido que voltou
        // do servidor não trazia os pagamentos de volta, então o retrato local
        // reclamou de "venda sem recebimento" de uma venda paga. O backend já
        // trata cadastro incompleto do jeito certo: monta a nota, grava a falha
        // nela e deixa o operador corrigir e reenviar.
        final settled = await _flushFiscalWithRetries('${order['id']}');
        if (!mounted) return;
        AppLogger.instance.info(
          'fiscal_flush_resultado',
          data: {
            'pedido': '${order['id']}',
            'entregue': settled != null,
            'issues': issues.length,
            'printable': settled?['printable'],
            'fiscal_state': settled?['fiscal_state'],
          },
        );
        if (settled != null) {
          final summary =
              'Pedido #${order['sequence']} · NFC-e ${settled['number'] ?? ''}';
          if (settled['printable'] == true) {
            await _printDanfe(
              invoiceId: '${settled['id']}',
              summary: summary,
              automatic: true,
            );
          } else {
            _showFiscalStateToast(settled, silent: silentIfUnconfigured);
            _watchFiscalAuthorization(settled, summary: summary);
          }
          return;
        }
        // Continua pendente mesmo depois de insistir: a nota fica na fila
        // fiscal local e sai pelo ciclo automático (30s) ou pela próxima
        // ação do operador — mas NINGUÉM fica vigiando essa autorização
        // para imprimir sozinho a partir daqui. O aviso não é opcional: era
        // aqui que a venda terminava só com o recibo, sem explicação
        // nenhuma, porque este toast ficava escondido atrás da mesma
        // bandeira que esconde "este restaurante não emite NFC-e".
        showAppToast(
          context,
          issues.isEmpty
              ? 'Venda concluída. A NFC-e ainda não foi confirmada com o '
                    'provedor fiscal e será emitida assim que possível — '
                    'acompanhe pelo histórico do pedido.'
              : 'Venda concluída, mas o cadastro fiscal está incompleto e a '
                    'NFC-e não vai passar assim: ${issues.first}',
          severity: AppErrorSeverity.warning,
        );
        return;
      }

      if (invoice['emitted'] == false) {
        if (!silentIfUnconfigured) {
          showAppToast(
            context,
            '${invoice['message'] ?? 'Nota fiscal não emitida: o provedor fiscal não está configurado.'}',
            severity: AppErrorSeverity.warning,
          );
        }
        return;
      }

      // `fiscal_state` é a situação real do documento; `status` sozinho não
      // separa "ainda não saiu daqui" de "pode ter sido emitida". Só um
      // documento AUTORIZADO tem chave que a SEFAZ reconhece — por isso o
      // DANFE só é oferecido quando `printable` vem verdadeiro.
      if (invoice['printable'] != true) {
        _showFiscalStateToast(invoice, silent: false);
        _watchFiscalAuthorization(
          invoice,
          summary:
              'Pedido #${order['sequence']} · NFC-e ${invoice['number'] ?? ''}',
        );
        return;
      }

      if (invoice['emission_type'] == '9') {
        showAppToast(
          context,
          'NFC-e emitida em contingência — será retransmitida quando a conexão com a SEFAZ voltar.',
          severity: AppErrorSeverity.warning,
        );
      }

      await _printDanfe(
        invoiceId: '${invoice['id']}',
        summary:
            'Pedido #${order['sequence']} · NFC-e ${invoice['number'] ?? ''}',
        automatic: true,
      );
    } finally {
      if (mounted) setState(() => emittingInvoice = false);
    }
  }

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
  }) {
    final invoiceId = '${invoice['id'] ?? ''}';
    final state = '${invoice['fiscal_state'] ?? ''}';
    // Só faz sentido esperar por uma nota que está a caminho. Recusa e erro de
    // configuração pedem correção humana; documento local ainda na fila (id
    // `offline-…`) nem existe no servidor para ser consultado.
    const inFlight = {'processing', 'awaiting_transmission'};
    if (invoiceId.isEmpty ||
        invoiceId.startsWith('offline-') ||
        !inFlight.contains(state)) {
      return;
    }
    // Um segundo vigia sobre a mesma nota mandaria o DANFE para a impressora
    // de novo — e a segunda via seria um cupom NOVO, porque o trabalho da
    // primeira já teria saído.
    if (!watchedFiscalInvoices.add(invoiceId)) return;
    unawaited(_pollFiscalAuthorization(invoiceId: invoiceId, summary: summary));
  }

  Future<void> _pollFiscalAuthorization({
    required String invoiceId,
    required String summary,
  }) async {
    try {
      await _pollFiscalAuthorizationNow(invoiceId: invoiceId, summary: summary);
    } finally {
      watchedFiscalInvoices.remove(invoiceId);
    }
  }

  Future<void> _pollFiscalAuthorizationNow({
    required String invoiceId,
    required String summary,
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
        await _printDanfe(
          invoiceId: invoiceId,
          summary: summary,
          automatic: true,
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
    if (!mounted) return;
    showAppToast(
      context,
      'A SEFAZ ainda não autorizou a NFC-e desta venda. Quando autorizar, '
      'imprima o DANFE pelo pedido em Pedidos.',
      severity: AppErrorSeverity.warning,
    );
  }

  /// Insiste em entregar a nota antes de desistir e avisar o operador.
  ///
  /// `flushFiscalForOrder` pode voltar `null` por um instante sem conexão, ou
  /// porque outro ciclo de sincronização já estava em voo — nenhum dos dois
  /// significa "sem rede para sempre". Poucas tentativas curtas cobrem isso
  /// sem prender o caixa: se depois delas ainda não resolveu, a nota segue
  /// pela fila e o operador é avisado.
  Future<Map<String, dynamic>?> _flushFiscalWithRetries(String orderId) async {
    const waits = [
      Duration.zero,
      Duration(milliseconds: 500),
      Duration(seconds: 1),
      Duration(seconds: 2),
      Duration(seconds: 3),
    ];
    for (final wait in waits) {
      if (wait > Duration.zero) await Future<void>.delayed(wait);
      if (!mounted) return null;
      final settled = await api.flushFiscalForOrder(orderId);
      if (settled != null) return settled;
    }
    return null;
  }

  /// Explica ao operador por que o cupom fiscal ainda nao saiu.
  void _showFiscalStateToast(
    Map<String, dynamic> invoice, {
    required bool silent,
  }) {
    if (!mounted) return;
    final state = '${invoice['fiscal_state'] ?? ''}';
    final blocking = state == 'rejected' || state == 'configuration_error';
    // Numa emissao automatica so o que exige acao humana interrompe o
    // operador; o resto segue seu curso pela fila.
    if (silent && !blocking) return;
    showAppToast(
      context,
      switch (state) {
        'rejected' =>
          'NFC-e recusada: ${invoice['error_message'] ?? 'verifique o cadastro fiscal do pedido'}. '
              'Não haverá reenvio automático.',
        'configuration_error' =>
          'NFC-e não emitida: a configuração fiscal está inválida '
              '(${invoice['error_message'] ?? 'certificado, token ou CSC'}).',
        'reconciliation_required' =>
          'A NFC-e pode ter sido emitida e a resposta se perdeu. Ela será '
              'consultada antes de qualquer reenvio — não emita de novo.',
        'processing' =>
          'NFC-e transmitida, aguardando autorização da SEFAZ. O cupom '
              'fiscal sai quando a autorização chegar.',
        _ =>
          'Venda concluída. A NFC-e ainda não foi transmitida e será '
              'enviada assim que a conexão voltar.',
      },
      severity: blocking ? AppErrorSeverity.failure : AppErrorSeverity.warning,
    );
  }

  /// Reimprime o DANFE de uma nota que ja esta autorizada.
  ///
  /// Nao passa pelo `/invoices/emit/`: a nota existe, o que falta e o papel —
  /// e sem rede aquela rota vira mais uma entrada na fila fiscal para um
  /// documento que ja foi emitido.
  Future<void> _reprintDanfe(Map<String, dynamic> order) async {
    final fiscal = order['fiscal'] as Map<String, dynamic>?;
    final invoiceId = '${fiscal?['id'] ?? ''}';
    if (invoiceId.isEmpty || emittingInvoice) return;
    setState(() => emittingInvoice = true);
    try {
      await _printDanfe(
        invoiceId: invoiceId,
        summary:
            'Pedido #${order['sequence']} · NFC-e ${fiscal?['number'] ?? ''}',
      );
    } finally {
      if (mounted) setState(() => emittingInvoice = false);
    }
  }

  /// Manda o DANFE para a impressora — a master do terminal, quando houver.
  /// Manda o DANFE para a impressora — a master do terminal, quando houver.
  ///
  /// `automatic` é a impressão que o gesto de concluir dispara sozinho. Ela não
  /// repete um DANFE que já saiu deste terminal: o servidor pode ter criado um
  /// cupom automático quando a autorização chegou, e o cliente receberia duas
  /// vias idênticas. A reimpressão pedida pelo operador ignora isso — quem
  /// clicou quer outra via.
  Future<void> _printDanfe({
    required String invoiceId,
    required String summary,
    bool automatic = false,
  }) async {
    final printers = await _list(
      '/printers/',
      query: {'restaurant': restaurantId, 'is_active': true, 'page_size': 100},
    );
    if (!mounted || printers.isEmpty) {
      AppLogger.instance.warning(
        'danfe_sem_impressora_cadastrada',
        data: {'nota': invoiceId, 'montado': mounted},
      );
      return;
    }
    // Se o caixa fixou uma impressora master, perguntar de novo aqui aparece
    // para ele como "o sistema ignorou a master".
    final master = widget.preferences.masterPrinterId;
    final hasMaster = printers.any((p) => '${p['id']}' == master);
    final printerId = hasMaster
        ? master
        : await showDialog<String>(
            context: context,
            builder: (_) => PrinterSelectionDialog(
              printers: printers,
              title: 'Imprimir DANFE NFC-e',
              summary: summary,
              description:
                  'O DANFE traz a chave de acesso e o QR Code de consulta da nota.',
            ),
          );
    if (printerId == null) {
      AppLogger.instance.warning(
        'danfe_sem_impressora_escolhida',
        data: {'nota': invoiceId, 'master': master},
      );
      return;
    }
    AppLogger.instance.info(
      'danfe_impressao_pedida',
      data: {
        'nota': invoiceId,
        'impressora': printerId,
        'automatico': automatic,
      },
    );
    final Map<String, dynamic> printJob;
    try {
      printJob = await api.post(
        '/invoices/$invoiceId/print/',
        body: {'printer': printerId},
        accessToken: token,
      );
    } catch (error) {
      if (mounted) _error(error, title: 'O DANFE não pôde ser gerado');
      return;
    }
    if (!mounted) return;
    final printer = printJob['printer'] as Map<String, dynamic>?;
    if (printer == null) {
      _error(
        const ApiException('A impressora selecionada não foi encontrada.'),
      );
      return;
    }
    final ok = await _printingStep(
      () =>
          deviceAgent.printJobManually(printJob, printer, automatic: automatic),
      title: 'O DANFE não saiu na impressora',
    );
    AppLogger.instance.info(
      'danfe_impressao_resultado',
      data: {
        'nota': invoiceId,
        'job': '${printJob['print_job_id'] ?? ''}',
        'impressora': '${printer['name'] ?? ''}',
        'ok': ok,
      },
    );
  }
}
