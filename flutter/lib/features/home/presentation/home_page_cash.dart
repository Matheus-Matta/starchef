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
}
