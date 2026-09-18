// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Operação do caixa: abrir, sangrar, suprir, aprovar movimento e fechar.
///
/// Separada da tela de divergência (`_CashSection`), que é um diálogo só.
/// O código foi MOVIDO, não reescrito.
mixin _CashOpsSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get cashSession;
  set cashSession(Map<String, dynamic>? value);
  bool get movementApprovalDialogOpen;
  set movementApprovalDialogOpen(bool value);
  Map<String, dynamic>? get pendingCashMovement;
  set pendingCashMovement(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get stations;
  double get cashBalance;
  bool get hasCashDivergence;
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
  Future<void> _refreshCashSession();
  // Comprovantes no papel (`_CashPrintSection`): saem DEPOIS de a operação
  // estar registrada, e uma impressora fora do ar nunca a desfaz.
  Future<void> _printCashOpening(Map<String, dynamic> session);
  Future<void> _printCashMovement(
    Map<String, dynamic> movement,
    Map<String, dynamic> session, {
    String authorizedBy,
    String managerReason,
  });
  Future<void> _printCashClosing(Map<String, dynamic> session);

  Future<void> _openCash() async {
    final userId = widget.controller.session!.user.id;
    final linked = stations
        .where(
          (station) => (station['operators'] as List? ?? [])
              .map((id) => '$id')
              .contains(userId),
        )
        .toList();
    if (linked.isEmpty) {
      _error(
        const ApiException('Seu usuário não está vinculado a nenhum caixa.'),
      );
      return;
    }
    var stationId = '${linked.first['id']}';
    final amount = TextEditingController(text: '0.00');
    final notes = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AppDialog(
          title: const Text('Abrir caixa'),
          content: SizedBox(
            width: 420,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                DropdownButtonFormField<String>(
                  initialValue: stationId,
                  isExpanded: true,
                  decoration: const InputDecoration(labelText: 'Caixa'),
                  items: linked
                      .map(
                        (station) => DropdownMenuItem(
                          value: '${station['id']}',
                          child: Text('${station['name']}'),
                        ),
                      )
                      .toList(),
                  onChanged: (value) => update(() => stationId = value!),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: amount,
                  keyboardType: const TextInputType.numberWithOptions(
                    decimal: true,
                  ),
                  decoration: const InputDecoration(
                    labelText: 'Valor de abertura',
                    prefixText: r'R$ ',
                  ),
                ),
                const SizedBox(height: 16),
                TextField(
                  controller: notes,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: 'Observação',
                    helperText:
                        'Registre alguma informação relevante sobre a abertura.',
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: const Text('Abrir caixa'),
            ),
          ],
        ),
      ),
    );
    if (confirmed == true) {
      final result = await _work(() async {
        cashSession = await api.post(
          '/cash-register/open/',
          body: {
            'cash_station': stationId,
            'opening_amount': amount.text.replaceAll(',', '.'),
            'notes': notes.text.trim(),
            ..._terminalIdentity,
          },
          accessToken: token,
        );
        setState(() {});
        return cashSession;
      }, onError: (error) => _cashError(error, 'abrir o caixa'));
      if (result != null) {
        await _printCashOpening(result);
        if (mounted) await _goHome();
      }
    }
  }

  Future<void> _cashMovement(String type) async {
    final amount = TextEditingController();
    final reason = TextEditingController();
    final destination = TextEditingController();
    final isWithdrawal = type == 'withdrawal';
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AppDialog(
        title: Text(
          isWithdrawal ? 'Registrar sangria' : 'Registrar suprimento',
        ),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Valor',
                  prefixText: r'R$ ',
                ),
              ),
              if (isWithdrawal) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: destination,
                  decoration: const InputDecoration(labelText: 'Destino'),
                ),
              ],
              const SizedBox(height: 12),
              TextField(
                controller: reason,
                maxLines: 2,
                decoration: const InputDecoration(
                  labelText: 'Motivo obrigatório',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      final movement = await _work(
        () async {
          return api.post(
            '/cash-register/${cashSession!['id']}/$type/',
            body: {
              'amount': amount.text.replaceAll(',', '.'),
              'reason': reason.text.trim(),
              'destination': destination.text.trim(),
              'source': destination.text.trim(),
              ..._terminalIdentity,
            },
            accessToken: token,
          );
        },
        onError: (error) => _cashError(
          error,
          isWithdrawal ? 'registrar a sangria' : 'registrar o suprimento',
        ),
      );
      if (movement == null) return;
      if (movement['status'] == 'pending') {
        // O comprovante sai quando a movimentação for autorizada.
        setState(() => pendingCashMovement = movement);
        await _showMovementApproval();
        return;
      }
      final session = cashSession;
      if (session != null) await _printCashMovement(movement, session);
    }
  }

  /// Autoriza a sangria/suprimento pendente com a senha de ações do caixa.
  ///
  /// Só ela: é conferida neste terminal contra o hash sincronizado e
  /// funciona sem internet ([_approveWithCashPassword]). O login de gerente
  /// que existia aqui como alternativa saiu — exigia servidor e a pergunta
  /// "qual usuário?" travava o operador com a gaveta aberta.
  Future<void> _showMovementApproval() async {
    final movement = pendingCashMovement;
    if (!mounted || movement == null || movementApprovalDialogOpen) return;
    movementApprovalDialogOpen = true;
    String? justificativa;
    try {
      // O diálogo é DONO dos próprios controladores, e por isso é ele quem os
      // descarta — no `dispose` do seu `State`, que o Flutter só chama depois
      // que a rota some de verdade.
      //
      // Criá-los aqui fora e descartá-los depois do `await showDialog` parece
      // igual e não é: esse `await` volta quando a rota é DESEMPILHADA, com a
      // animação de saída ainda rodando. Descartar ali deixava o campo da
      // senha, ainda na tela por mais alguns quadros, apontando para um
      // controlador morto — "A TextEditingController was used after being
      // disposed", e a árvore meio desmontada logo em seguida.
      justificativa = await showDialog<String>(
        context: context,
        barrierDismissible: true,
        builder: (dialogContext) => _MovementApprovalForm(
          movement: movement,
          onApprove: (password, reason) async {
            await _approveWithCashPassword(
              password: password,
              reason: reason,
              movementId: '${movement['id']}',
            );
            pendingCashMovement = null;
          },
          onError: (error) {
            if (mounted) _error(error);
          },
        ),
      );
    } finally {
      movementApprovalDialogOpen = false;
    }

    // FORA do diálogo. Recarregar a tela e imprimir o comprovante levam
    // segundos e podem falhar (a impressora, a rota do documento). Enquanto
    // isso rodava dentro do callback do botão, o `showDialog` já havia
    // retornado — e o `catch` daquele callback reconstruía um diálogo morto.
    if (justificativa == null || !mounted) return;
    await _load();
    await _printApprovedMovement(
      movement,
      authorizedBy: 'Senha de ações do caixa',
      managerReason: justificativa,
    );
  }

  /// Comprovante da sangria/suprimento recém-autorizado.
  Future<void> _printApprovedMovement(
    Map<String, dynamic> movement, {
    required String authorizedBy,
    required String managerReason,
  }) async {
    final session = cashSession;
    if (!mounted || session == null) return;
    await _printCashMovement(
      {...movement, 'status': 'approved'},
      session,
      authorizedBy: authorizedBy,
      managerReason: managerReason,
    );
  }

  Future<void> _closeCash() async {
    final amount = TextEditingController();
    final notes = TextEditingController();
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AppDialog(
        title: const Text('Fechar caixa'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                decoration: const InputDecoration(
                  labelText: 'Valor contado',
                  helperText:
                      'Informe o dinheiro físico contado no fechamento.',
                  prefixText: r'R$ ',
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: notes,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Observação',
                  helperText:
                      'Informe ocorrências ou justificativas do fechamento.',
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Confirmar fechamento'),
          ),
        ],
      ),
    );
    if (confirmed == true) {
      final closed = await _work(() async {
        cashSession = await api.post(
          '/cash-register/${cashSession!['id']}/close/',
          body: {
            'actual_amount': amount.text.replaceAll(',', '.'),
            'notes': notes.text.trim(),
            ..._terminalIdentity,
          },
          accessToken: token,
        );
        setState(() {});
        return cashSession;
      }, onError: (error) => _cashError(error, 'fechar o caixa'));
      if (closed != null) await _printCashClosing(closed);
    }
  }

  void _onCashMenuSelected(String value) {
    if (value == 'toggle_balance') {
      unawaited(_toggleCashBalanceVisibility());
      return;
    }
    if (value == 'supply' || value == 'withdrawal') {
      _cashMovement(value);
    }
    if (value == 'close') _closeCash();
  }

  List<PopupMenuEntry<String>> _cashMenuItems() => [
    PopupMenuItem(
      value: 'toggle_balance',
      child: ListTile(
        leading: Icon(
          _canSeeCashBalance
              ? Icons.visibility_off_outlined
              : Icons.visibility_outlined,
        ),
        title: Text(_canSeeCashBalance ? 'Ocultar saldo' : 'Ver saldo'),
      ),
    ),
    const PopupMenuDivider(),
    const PopupMenuItem(
      value: 'supply',
      child: ListTile(
        leading: Icon(Icons.add_circle_outline),
        title: Text('Suprimento'),
      ),
    ),
    const PopupMenuItem(
      value: 'withdrawal',
      child: ListTile(
        leading: Icon(Icons.remove_circle_outline),
        title: Text('Sangria'),
      ),
    ),
    const PopupMenuDivider(),
    const PopupMenuItem(
      value: 'close',
      child: ListTile(leading: Icon(Icons.lock), title: Text('Fechar caixa')),
    ),
  ];
}

/// O formulário da autorização de sangria/suprimento.
///
/// Existe como widget com estado por um motivo só, e é o que evita a tela
/// vermelha: os `TextEditingController` são criados no `initState` e
/// descartados no `dispose`, que o Flutter chama depois que a rota do diálogo
/// termina de sair. Quem cria e descarta de fora, em volta do
/// `await showDialog`, descarta cedo demais.
///
/// Devolve a justificativa gerencial pelo `Navigator.pop`, ou `null` quando o
/// operador minimiza sem autorizar.
class _MovementApprovalForm extends StatefulWidget {
  const _MovementApprovalForm({
    required this.movement,
    required this.onApprove,
    required this.onError,
  });

  final Map<String, dynamic> movement;

  /// Autoriza no servidor. Lança quando a senha é recusada.
  final Future<void> Function(String password, String reason) onApprove;
  final void Function(Object error) onError;

  @override
  State<_MovementApprovalForm> createState() => _MovementApprovalFormState();
}

class _MovementApprovalFormState extends State<_MovementApprovalForm> {
  final _password = TextEditingController();
  final _managerReason = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _authorizing = false;

  @override
  void dispose() {
    _password.dispose();
    _managerReason.dispose();
    super.dispose();
  }

  Future<void> _authorize() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _authorizing = true);
    final justificativa = _managerReason.text.trim();
    try {
      await widget.onApprove(_password.text, justificativa);
    } catch (error) {
      if (!mounted) return;
      widget.onError(error);
      // O diálogo continua vivo: a recusa foi da senha ou do servidor, e o
      // campo guarda o que foi digitado para o operador corrigir.
      setState(() => _authorizing = false);
      return;
    }
    if (!mounted) return;
    Navigator.pop(context, justificativa);
  }

  @override
  Widget build(BuildContext context) => AppDialog(
    title: Text(
      widget.movement['movement_type'] == 'withdrawal'
          ? 'Autorizar sangria'
          : 'Autorizar suprimento',
    ),
    content: SizedBox(
      width: 480,
      child: Form(
        key: _formKey,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Movimentação pendente de '
                '${ValueFormatters.money(ValueFormatters.number(widget.movement['amount']).abs())}.',
                style: const TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 5),
              Text('Motivo: ${widget.movement['reason']}'),
              if ('${widget.movement['destination'] ?? ''}'.isNotEmpty)
                Text('Destino: ${widget.movement['destination']}'),
              const Divider(height: 30),
              TextFormField(
                controller: _password,
                autofocus: true,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: 'Senha de ações do caixa',
                  helperText: 'Definida no cadastro do restaurante.',
                  prefixIcon: Icon(Icons.lock_outline),
                ),
                validator: (value) => value == null || value.isEmpty
                    ? 'Informe a senha de ações do caixa.'
                    : null,
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _managerReason,
                maxLines: 3,
                decoration: const InputDecoration(
                  labelText: 'Justificativa gerencial',
                ),
                validator: (value) => value == null || value.trim().isEmpty
                    ? 'Informe a justificativa.'
                    : null,
              ),
            ],
          ),
        ),
      ),
    ),
    actions: [
      TextButton.icon(
        onPressed: _authorizing ? null : () => Navigator.pop(context),
        icon: const Icon(Icons.minimize),
        label: const Text('Minimizar'),
      ),
      FilledButton.icon(
        onPressed: _authorizing ? null : _authorize,
        icon: _authorizing
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : const Icon(Icons.verified_user_outlined),
        label: const Text('Autorizar movimentação'),
      ),
    ],
  );
}
