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

  /// Divergência no fechamento: só a senha de ações do caixa libera.
  ///
  /// Já houve aqui um segundo modo, "login de gerente" (usuário + senha na
  /// Retaguarda). Saiu: a senha do caixa é conferida neste terminal contra o
  /// hash sincronizado e funciona sem internet ([_approveWithCashPassword]);
  /// o login de gerente não, e a pergunta "qual usuário?" travava o
  /// operador no fim do turno.
  Future<void> _showCashDivergence() async {
    if (!mounted || !hasCashDivergence || divergenceDialogOpen) return;
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
          ),
        ),
      );
    } finally {
      divergenceDialogOpen = false;
    }

    if (aprovada == null || !mounted) return;
    cashSession = aprovada;
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


/// O formulário da aprovação de divergência de caixa.
///
/// Mesmo motivo de `_MovementApprovalForm`: os controladores vivem no `State`
/// e são descartados quando a rota do diálogo termina de sair — não quando o
/// `await showDialog` retorna, que é cedo demais.
///
/// Devolve a sessão de caixa já aprovada, ou `null` se nada foi autorizado.
class _CashDivergenceForm extends StatefulWidget {
  const _CashDivergenceForm({
    required this.session,
    required this.expected,
    required this.counted,
    required this.difference,
    required this.buildValue,
    required this.onApprove,
    required this.onError,
    required this.onLogout,
  });

  final Map<String, dynamic>? session;
  final String expected;
  final String counted;
  final String difference;
  final Widget Function(String label, String value, {bool emphasized})
  buildValue;
  final Future<Map<String, dynamic>> Function(String password, String reason)
  onApprove;
  final void Function(Object error) onError;
  final Future<void> Function() onLogout;

  @override
  State<_CashDivergenceForm> createState() => _CashDivergenceFormState();
}

class _CashDivergenceFormState extends State<_CashDivergenceForm> {
  final _password = TextEditingController();
  final _reason = TextEditingController();
  final _formKey = GlobalKey<FormState>();
  bool _authorizing = false;

  @override
  void dispose() {
    _password.dispose();
    _reason.dispose();
    super.dispose();
  }

  Future<void> _authorize() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() => _authorizing = true);
    final Map<String, dynamic> aprovada;
    try {
      aprovada = await widget.onApprove(_password.text, _reason.text.trim());
    } catch (error) {
      if (!mounted) return;
      widget.onError(error);
      // O diálogo segue vivo: a senha foi recusada e o operador corrige o que
      // digitou, sem redigitar tudo.
      setState(() => _authorizing = false);
      return;
    }
    if (!mounted) return;
    Navigator.pop(context, aprovada);
  }

  @override
  Widget build(BuildContext context) {
    final notes = '${widget.session?['notes'] ?? ''}'.trim();
    return AppDialog(
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
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'O PDV permanecerá bloqueado até que o fechamento '
                  'seja autorizado com a senha de ações do caixa.',
                ),
                const SizedBox(height: 18),
                widget.buildValue('Valor esperado', widget.expected),
                widget.buildValue('Valor contado', widget.counted),
                widget.buildValue(
                  'Diferença',
                  widget.difference,
                  emphasized: true,
                ),
                if (notes.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text('Observação: $notes'),
                ],
                const Divider(height: 32),
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
                  controller: _reason,
                  maxLines: 3,
                  decoration: const InputDecoration(
                    labelText: 'Justificativa gerencial',
                    helperText:
                        'Explique por que a divergência está sendo aprovada.',
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
          onPressed: _authorizing
              ? null
              : () async {
                  Navigator.pop(context);
                  await widget.onLogout();
                },
          icon: const Icon(Icons.logout),
          label: const Text('Sair do sistema'),
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
          label: const Text('Aprovar e concluir fechamento'),
        ),
      ],
    );
  }
}
