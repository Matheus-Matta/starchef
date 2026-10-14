// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O formulário da autorização de sangria/suprimento.
///
/// Existe como widget com estado por um motivo só, e é o que evita a tela
/// vermelha: os `TextEditingController` são criados no `initState` e
/// descartados no `dispose`, que o Flutter chama depois que a rota do diálogo
/// termina de sair. Quem cria e descarta de fora, em volta do
/// `await showDialog`, descarta cedo demais.
///
/// Devolve a justificativa gerencial pelo `Navigator.pop`, ou `null` quando o
/// operador minimiza sem autorizar — ou desiste da movimentação.
class _MovementApprovalForm extends StatefulWidget {
  const _MovementApprovalForm({
    required this.movement,
    required this.onApprove,
    required this.onError,
    required this.onCancel,
  });

  final Map<String, dynamic> movement;

  /// Autoriza no servidor. Lança quando a senha é recusada.
  final Future<void> Function(String password, String reason) onApprove;
  final void Function(Object error) onError;

  /// Desiste da movimentação: ela vira cancelada e sai da fila, sem senha.
  final Future<void> Function() onCancel;

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

  Future<void> _cancel() async {
    setState(() => _authorizing = true);
    try {
      await widget.onCancel();
    } catch (error) {
      if (!mounted) return;
      widget.onError(error);
      setState(() => _authorizing = false);
      return;
    }
    if (mounted) Navigator.pop(context);
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
              if ('${widget.movement['reason'] ?? ''}'.trim().isNotEmpty)
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
      TextButton.icon(
        key: const Key('cash-movement-cancel'),
        onPressed: _authorizing ? null : _cancel,
        icon: const Icon(Icons.undo),
        label: Text(
          widget.movement['movement_type'] == 'withdrawal'
              ? 'Cancelar sangria'
              : 'Cancelar suprimento',
        ),
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
