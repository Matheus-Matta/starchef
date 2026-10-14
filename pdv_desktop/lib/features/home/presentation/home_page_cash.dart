// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Caixa: abertura, sangria e suprimento, aprovação de divergência e
/// fechamento.
///
/// Os métodos foram MOVIDOS, não reescritos. O que a seção usa de fora está
/// declarado abaixo como membro abstrato — é o contrato explícito dela com o
/// resto da tela, e ele falha na compilação se um lado mudar sem o outro.
mixin _CashSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get cashSession;
  set cashSession(Map<String, dynamic>? value);
  bool get divergenceDialogOpen;
  set divergenceDialogOpen(bool value);
  bool get movementApprovalDialogOpen;
  set movementApprovalDialogOpen(bool value);
  Map<String, dynamic>? get pendingCashMovement;
  set pendingCashMovement(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get stations;
  bool get hasCashDivergence;
  double get cashBalance;
  bool get _canSeeCashBalance;
  Map<String, dynamic> get _terminalIdentity;

  void _cashError(Object error, String operation);
  Future<Map<String, dynamic>> _approveWithCashPassword({
    required String password,
    required String reason,
    String? movementId,
  });
  Future<void> _toggleCashBalanceVisibility();
  Future<void> _goHome();
  Future<void> _load();
  Future<void> _printCashOpeningDivergence(Map<String, dynamic> session);
  Future<void> _printCashClosing(
    Map<String, dynamic> session, {
    bool abrirGaveta,
  });

  /// Divergência no fechamento: só a senha de ações do caixa libera.
  ///
  /// Já houve aqui um segundo modo, "login de gerente" (usuário + senha na
  /// Retaguarda). Saiu: a senha do caixa é conferida neste terminal contra o
  /// hash sincronizado e funciona sem internet ([_approveWithCashPassword]);
  /// o login de gerente não, e a pergunta "qual usuário?" travava o
  /// operador no fim do turno.
  Future<void> _showCashDivergence() async {
    if (!mounted || !hasCashDivergence || divergenceDialogOpen) return;
    final pendingOperation = '${cashSession?['pending_operation'] ?? ''}';
    final sessionId = '${cashSession?['id'] ?? ''}';
    divergenceDialogOpen = true;
    Map<String, dynamic>? aprovada;
    try {
      // Os controladores são do diálogo, não deste método: ver
      // `_MovementApprovalForm` para o porquê — `await showDialog` volta com a
      // animação de saída ainda rodando, e descartar ali deixa o campo da
      // senha apontando para um controlador morto.
      aprovada = await showDialog<Map<String, dynamic>>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => PopScope(
          canPop: false,
          child: _CashDivergenceForm(
            session: cashSession,
            expected: _money(cashSession?['expected_amount']),
            counted: _money(cashSession?['actual_amount']),
            difference: _differenceText(cashSession?['difference_amount']),
            buildValue: _divergenceValue,
            onApprove: (password, reason) =>
                _approveWithCashPassword(reason: reason, password: password),
            onError: (error) {
              if (mounted) _error(error);
            },
            onLogout: () => widget.controller.logout(),
            onCancelClosing: pendingOperation == 'closing'
                ? () => api.post(
                    '/cash-register/$sessionId/cancel-pending/',
                    body: {..._terminalIdentity},
                    accessToken: token,
                  )
                : null,
          ),
        ),
      );
    } finally {
      divergenceDialogOpen = false;
    }

    if (aprovada == null || !mounted) return;
    cashSession = aprovada;
    final reaberto = '${aprovada['status']}' == 'open';
    if (pendingOperation == 'opening') {
      await _printCashOpeningDivergence(aprovada);
    } else if (pendingOperation == 'closing' && reaberto) {
      showAppToast(
        context,
        'Fechamento cancelado. O caixa continua aberto.',
        severity: AppErrorSeverity.info,
      );
    } else if (pendingOperation == 'closing') {
      // O relatório sai DEPOIS da senha: antes dela o fechamento ainda pode
      // ser cancelado, e o papel assinado mostraria um caixa que não fechou.
      await _printCashClosing(aprovada);
    }
    // FORA do diálogo: `_load` leva segundos e pode falhar. Dentro do callback
    // do botão, ele corria depois de o `showDialog` já ter retornado.
    await _load();
  }

  Widget _divergenceValue(
    String label,
    String value, {
    bool emphasized = false,
  }) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 5),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        Text(label),
        Text(
          value,
          style: TextStyle(
            fontSize: emphasized ? 18 : 16,
            fontWeight: FontWeight.w900,
            color: emphasized ? Theme.of(context).colorScheme.error : null,
          ),
        ),
      ],
    ),
  );

  String _differenceText(dynamic value) {
    final difference = _number(value);
    final description = difference < 0
        ? 'falta'
        : difference > 0
        ? 'sobra'
        : 'sem diferença';
    return '${_money(difference.abs())} ($description)';
  }
}
