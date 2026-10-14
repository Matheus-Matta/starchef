// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O formulário da aprovação de divergência de caixa.
///
/// Mesmo motivo de `_MovementApprovalForm`: os controladores vivem no `State`
/// e são descartados quando a rota do diálogo termina de sair — não quando o
/// `await showDialog` retorna, que é cedo demais.
///
/// Devolve a sessão de caixa já aprovada — ou, quando o operador desiste do
/// fechamento, a sessão REABERTA (`status` `open`) —, ou `null` se nada mudou.
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
    this.onCancelClosing,
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

  /// Desiste do fechamento: o caixa volta a ficar aberto, sem senha. `null`
  /// na divergência de ABERTURA, que não tem um "antes" para onde voltar.
  final Future<Map<String, dynamic>> Function()? onCancelClosing;

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
    await _run(() => widget.onApprove(_password.text, _reason.text.trim()));
  }

  Future<void> _run(Future<Map<String, dynamic>> Function() gesto) async {
    setState(() => _authorizing = true);
    final Map<String, dynamic> aprovada;
    try {
      aprovada = await gesto();
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
    final opening = widget.session?['pending_operation'] == 'opening';
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
                Text(
                  opening
                      ? 'O PDV permanecerá bloqueado até que a divergência '
                            'seja autorizada com a senha de ações do caixa.'
                      : 'Autorize com a senha de ações do caixa, ou cancele '
                            'o fechamento para contar de novo — o caixa volta '
                            'a ficar aberto.',
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
        if (widget.onCancelClosing case final cancelar?)
          TextButton.icon(
            key: const Key('cash-divergence-cancel-closing'),
            onPressed: _authorizing ? null : () => _run(cancelar),
            icon: const Icon(Icons.undo),
            label: const Text('Cancelar fechamento'),
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
          label: Text(
            opening
                ? 'Autorizar abertura divergente'
                : 'Aprovar e concluir fechamento',
          ),
        ),
      ],
    );
  }
}
