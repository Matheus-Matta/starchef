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
  bool get cashSessionFromCache;
  set cashSessionFromCache(bool value);
  bool get divergenceDialogOpen;
  set divergenceDialogOpen(bool value);
  bool get movementApprovalDialogOpen;
  set movementApprovalDialogOpen(bool value);
  Map<String, dynamic>? get pendingCashMovement;
  set pendingCashMovement(Map<String, dynamic>? value);
  List<Map<String, dynamic>> get stations;
  int get offlinePendingCount;
  bool get hasCashDivergence;
  double get cashBalance;
  bool get _canSeeCashBalance;
  Map<String, dynamic> get _terminalIdentity;

  void _cashError(Object error, String operation);
  Future<Map<String, dynamic>> _approveWithCashPassword({
    required String password,
    required String reason,
  });
  Future<void> _toggleCashBalanceVisibility();
  Future<void> _goHome();
  Future<void> _load();

  Future<void> _showCashDivergence() async {
    if (!mounted || !hasCashDivergence || divergenceDialogOpen) return;
    divergenceDialogOpen = true;
    final username = TextEditingController();
    final password = TextEditingController();
    final cashPassword = TextEditingController();
    final reason = TextEditingController();
    final formKey = GlobalKey<FormState>();
    var authorizing = false;
    // Modo de autorização: false = login de gerente (online) / true = senha do
    // caixa do restaurante (verificável offline).
    var cashMode = false;
    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => PopScope(
          canPop: false,
          child: StatefulBuilder(
            builder: (context, update) => AppDialog(
              title: const Row(
                children: [
                  Icon(Icons.warning_amber_rounded, color: Colors.orange),
                  SizedBox(width: 10),
                  Expanded(child: Text('Divergência no caixa')),
                ],
              ),
              content: SizedBox(
                width: 520,
                child: Form(
                  key: formKey,
                  child: SingleChildScrollView(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          'O PDV permanecerá bloqueado até que um gerente autorizado resolva o fechamento.',
                        ),
                        const SizedBox(height: 18),
                        _divergenceValue(
                          'Valor esperado',
                          _money(cashSession?['expected_amount']),
                        ),
                        _divergenceValue(
                          'Valor contado',
                          _money(cashSession?['actual_amount']),
                        ),
                        _divergenceValue(
                          'Diferença',
                          _differenceText(cashSession?['difference_amount']),
                          emphasized: true,
                        ),
                        if ('${cashSession?['notes'] ?? ''}'
                            .trim()
                            .isNotEmpty) ...[
                          const SizedBox(height: 8),
                          Text('Observação: ${cashSession!['notes']}'),
                        ],
                        const Divider(height: 32),
                        Align(
                          alignment: Alignment.centerLeft,
                          child: TextButton.icon(
                            onPressed: authorizing
                                ? null
                                : () => update(() => cashMode = !cashMode),
                            icon: Icon(
                              cashMode
                                  ? Icons.person_outline
                                  : Icons.password_outlined,
                            ),
                            label: Text(
                              cashMode
                                  ? 'Usar login de gerente'
                                  : 'Usar senha do caixa',
                            ),
                          ),
                        ),
                        const SizedBox(height: 6),
                        if (!cashMode) ...[
                          TextFormField(
                            controller: username,
                            autofocus: true,
                            decoration: const InputDecoration(
                              labelText: 'Usuário autorizador',
                              helperText:
                                  'Gerente, administrador ou proprietário.',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                value == null || value.trim().isEmpty
                                ? 'Informe o usuário autorizador.'
                                : null,
                          ),
                          const SizedBox(height: 14),
                          TextFormField(
                            controller: password,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Senha',
                              helperText:
                                  'A credencial será descartada após a autorização.',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Informe a senha.'
                                : null,
                          ),
                        ] else ...[
                          TextFormField(
                            controller: cashPassword,
                            autofocus: true,
                            obscureText: true,
                            decoration: const InputDecoration(
                              labelText: 'Senha do caixa',
                              helperText:
                                  'Senha de ações do caixa definida no restaurante — dispensa login de gerente.',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) => value == null || value.isEmpty
                                ? 'Informe a senha do caixa.'
                                : null,
                          ),
                        ],
                        const SizedBox(height: 14),
                        TextFormField(
                          controller: reason,
                          maxLines: 3,
                          decoration: const InputDecoration(
                            labelText: 'Justificativa gerencial',
                            helperText:
                                'Explique por que a divergência está sendo aprovada.',
                          ),
                          validator: (value) =>
                              value == null || value.trim().isEmpty
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
                  onPressed: authorizing
                      ? null
                      : () async {
                          Navigator.pop(dialogContext);
                          await widget.controller.logout();
                        },
                  icon: const Icon(Icons.logout),
                  label: const Text('Sair do sistema'),
                ),
                FilledButton.icon(
                  onPressed: authorizing
                      ? null
                      : () async {
                          if (!formKey.currentState!.validate()) return;
                          update(() => authorizing = true);
                          // Modo "senha do caixa": o servidor verifica a senha do
                          // restaurante e aprova — sem precisar de login de gerente.
                          if (cashMode) {
                            try {
                              cashSession = await _approveWithCashPassword(
                                reason: reason.text.trim(),
                                password: cashPassword.text,
                              );
                              if (dialogContext.mounted) {
                                Navigator.pop(dialogContext);
                              }
                              await _load();
                            } catch (error) {
                              if (mounted) _error(error);
                              update(() => authorizing = false);
                            } finally {
                              cashPassword.clear();
                            }
                            return;
                          }
                          String? temporaryAccess;
                          String? temporaryRefresh;
                          try {
                            final login = await api.post(
                              '/auth/login/',
                              body: {
                                'username': username.text.trim(),
                                'password': password.text,
                                // Autorização gerencial temporária: só usa o token
                                // (Bearer), sem cookies do navegador.
                                'no_cookie': true,
                              },
                            );
                            temporaryAccess = '${login['access']}';
                            temporaryRefresh = '${login['refresh']}';
                            final user = login['user'] as Map<String, dynamic>?;
                            final allowed =
                                user?['is_superuser'] == true ||
                                {
                                  'admin',
                                  'owner',
                                  'manager',
                                }.contains('${user?['profile_type']}');
                            if (!allowed) {
                              throw const ApiException(
                                'O usuário informado não possui permissão gerencial.',
                                statusCode: 403,
                              );
                            }
                            cashSession = await api.post(
                              '/cash-register/${cashSession!['id']}/approve/',
                              body: {'reason': reason.text.trim()},
                              accessToken: temporaryAccess,
                            );
                            if (dialogContext.mounted) {
                              Navigator.pop(dialogContext);
                            }
                            await _load();
                          } catch (error) {
                            if (mounted) _error(error);
                            update(() => authorizing = false);
                          } finally {
                            password.clear();
                            if (temporaryAccess != null &&
                                temporaryRefresh != null) {
                              try {
                                await api.post(
                                  '/auth/logout/',
                                  body: {
                                    'refresh': temporaryRefresh,
                                    'no_cookie': true,
                                  },
                                  accessToken: temporaryAccess,
                                );
                              } catch (_) {}
                            }
                          }
                        },
                  icon: authorizing
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.verified_user_outlined),
                  label: const Text('Aprovar e concluir fechamento'),
                ),
              ],
            ),
          ),
        ),
      );
    } finally {
      divergenceDialogOpen = false;
      username.dispose();
      password.dispose();
      cashPassword.dispose();
      reason.dispose();
    }
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
          // Abrir caixa passou a funcionar sem internet (§30): o repositório
          // precisa do nome do caixa e do operador para montar a sessão local
          // completa enquanto a operação espera na fila.
          localContext: {
            'cash_station': stations.cast<Map<String, dynamic>?>().firstWhere(
              (item) => '${item?['id']}' == stationId,
              orElse: () => null,
            ),
            'operator_name': widget.controller.session?.user.name,
          },
        );
        setState(() {});
        return cashSession;
      }, onError: (error) => _cashError(error, 'abrir o caixa'));
      if (result != null) {
        await _goHome();
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
      if (movement != null && movement['status'] == 'pending') {
        setState(() => pendingCashMovement = movement);
        await _showMovementApproval();
      }
    }
  }

  Future<void> _showMovementApproval() async {
    final movement = pendingCashMovement;
    if (!mounted || movement == null || movementApprovalDialogOpen) return;
    movementApprovalDialogOpen = true;
    final username = TextEditingController();
    final password = TextEditingController();
    final managerReason = TextEditingController();
    final formKey = GlobalKey<FormState>();
    var authorizing = false;
    try {
      await showDialog<void>(
        context: context,
        barrierDismissible: true,
        builder: (dialogContext) => StatefulBuilder(
          builder: (context, update) => AppDialog(
            title: Text(
              movement['movement_type'] == 'withdrawal'
                  ? 'Autorizar sangria'
                  : 'Autorizar suprimento',
            ),
            content: SizedBox(
              width: 480,
              child: Form(
                key: formKey,
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Movimentação pendente de ${_money(_number(movement['amount']).abs())}.',
                        style: const TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.w900,
                        ),
                      ),
                      const SizedBox(height: 5),
                      Text('Motivo: ${movement['reason']}'),
                      if ('${movement['destination'] ?? ''}'.isNotEmpty)
                        Text('Destino: ${movement['destination']}'),
                      const Divider(height: 30),
                      TextFormField(
                        controller: username,
                        autofocus: true,
                        decoration: const InputDecoration(
                          labelText: 'Usuário autorizador',
                          helperText: 'Gerente, administrador ou proprietário.',
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
                            ? 'Informe o usuário.'
                            : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: password,
                        obscureText: true,
                        decoration: const InputDecoration(labelText: 'Senha'),
                        validator: (value) => value == null || value.isEmpty
                            ? 'Informe a senha.'
                            : null,
                      ),
                      const SizedBox(height: 14),
                      TextFormField(
                        controller: managerReason,
                        maxLines: 3,
                        decoration: const InputDecoration(
                          labelText: 'Justificativa gerencial',
                        ),
                        validator: (value) =>
                            value == null || value.trim().isEmpty
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
                onPressed: authorizing
                    ? null
                    : () => Navigator.pop(dialogContext),
                icon: const Icon(Icons.minimize),
                label: const Text('Minimizar'),
              ),
              FilledButton.icon(
                onPressed: authorizing
                    ? null
                    : () async {
                        if (!formKey.currentState!.validate()) return;
                        update(() => authorizing = true);
                        String? temporaryAccess;
                        String? temporaryRefresh;
                        try {
                          final login = await api.post(
                            '/auth/login/',
                            body: {
                              'username': username.text.trim(),
                              'password': password.text,
                            },
                          );
                          temporaryAccess = '${login['access']}';
                          temporaryRefresh = '${login['refresh']}';
                          final user = login['user'] as Map<String, dynamic>?;
                          final allowed =
                              user?['is_superuser'] == true ||
                              {
                                'admin',
                                'owner',
                                'manager',
                              }.contains('${user?['profile_type']}');
                          if (!allowed) {
                            throw const ApiException(
                              'O usuário informado não possui permissão gerencial.',
                              statusCode: 403,
                            );
                          }
                          await api.post(
                            '/cash-register/${cashSession!['id']}/approve/',
                            body: {
                              'movement': movement['id'],
                              'reason': managerReason.text.trim(),
                            },
                            accessToken: temporaryAccess,
                          );
                          pendingCashMovement = null;
                          if (dialogContext.mounted) {
                            Navigator.pop(dialogContext);
                          }
                          await _load();
                        } catch (error) {
                          if (mounted) _error(error);
                          update(() => authorizing = false);
                        } finally {
                          password.clear();
                          if (temporaryAccess != null &&
                              temporaryRefresh != null) {
                            try {
                              await api.post(
                                '/auth/logout/',
                                body: {'refresh': temporaryRefresh},
                                accessToken: temporaryAccess,
                              );
                            } catch (_) {}
                          }
                        }
                      },
                icon: authorizing
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.verified_user_outlined),
                label: const Text('Autorizar movimentação'),
              ),
            ],
          ),
        ),
      );
    } finally {
      movementApprovalDialogOpen = false;
      username.dispose();
      password.dispose();
      managerReason.dispose();
    }
  }

  Future<void> _closeCash() async {
    // Operação na fila NÃO impede mais o fechamento. O saldo esperado sai dos
    // movimentos gravados NESTE terminal, e a venda offline já entrou na
    // gaveta local no momento do recebimento (`registerLocalSale`) — o número
    // conferido é o mesmo com ou sem rede. Bloquear aqui prendia o operador
    // no fim do turno esperando uma conexão que podia não voltar hoje.
    final pending = offlinePendingCount;
    final pendingNotice = pending == 1
        ? '1 operação ainda não subiu para o servidor.'
        : '$pending operações ainda não subiram para o servidor.';
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
              if (pending > 0) ...[
                // O operador precisa saber COM O QUE está conferindo — não
                // ser impedido de encerrar o turno por causa disso.
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.cloud_off_outlined, size: 18),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        '$pendingNotice O fechamento usa o que está gravado '
                        'neste terminal; a fila sobe quando a conexão voltar.',
                        style: TextStyle(
                          fontSize: 12,
                          color: Theme.of(context).colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
              ],
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
      await _work(() async {
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
      }, onError: (error) => _cashError(error, 'fechar o caixa'));
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
