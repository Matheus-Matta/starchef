// Ver `home_page.dart` para o motivo deste ignore na biblioteca.
// ignore_for_file: unused_element, unused_element_parameter
part of 'home_page.dart';

class _FinishOrderChoice {
  const _FinishOrderChoice({
    required this.chargeService,
    required this.fiscalCpf,
    required this.couponCode,
  });

  final bool chargeService;

  /// Só dígitos, ou vazio quando o CPF não vai na nota.
  final String fiscalCpf;

  /// O código do cupom, ou vazio para RETIRAR o cupom deste pedido.
  ///
  /// Vazio significa "sem cupom", e não "não mexe": o caixa pode ter apagado o
  /// código de propósito porque o cliente desistiu dele.
  final String couponCode;
}

/// As duas escolhas da nota: taxa de serviço e CPF.
///
/// É um widget com estado porque ele é DONO do `TextEditingController` — ver
/// `_MovementApprovalForm` para o defeito que isso evita.
class _FinishOrderForm extends StatefulWidget {
  const _FinishOrderForm({
    required this.chargeService,
    required this.savedCpf,
    required this.customerCpf,
    required this.serviceFeePercent,
    required this.serviceFeeAmount,
    required this.money,
    this.savedCoupon = '',
    this.couponDiscount = 0,
  });

  final bool chargeService;
  final String savedCpf;
  final String customerCpf;

  /// O cupom que JÁ está no pedido, e o quanto ele está abatendo agora.
  ///
  /// Reabrir o fechamento para corrigir a taxa não pode fazer o caixa digitar o
  /// cupom de novo — nem deixar dúvida sobre se ele continua valendo.
  final String savedCoupon;
  final double couponDiscount;
  final double serviceFeePercent;
  final double serviceFeeAmount;
  final String Function(dynamic value) money;

  @override
  State<_FinishOrderForm> createState() => _FinishOrderFormState();
}

class _FinishOrderFormState extends State<_FinishOrderForm> {
  late var _chargeService = widget.chargeService;
  late var _includeCpf = widget.savedCpf.isNotEmpty;
  late final _cpf = TextEditingController(
    text: formatCpf(
      widget.savedCpf.isNotEmpty ? widget.savedCpf : widget.customerCpf,
    ),
  );
  late final _cupom = TextEditingController(text: widget.savedCoupon);
  String? _cpfError;

  @override
  void dispose() {
    _cpf.dispose();
    _cupom.dispose();
    super.dispose();
  }

  void _confirm() {
    if (_includeCpf && !isValidCpf(_cpf.text)) {
      setState(() => _cpfError = 'Informe um CPF válido.');
      return;
    }
    Navigator.pop(
      context,
      _FinishOrderChoice(
        chargeService: _chargeService,
        fiscalCpf: _includeCpf ? cpfDigits(_cpf.text) : '',
        couponCode: _cupom.text.trim().toUpperCase(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => AppDialog(
    title: const Text('Ir para o pagamento'),
    content: SizedBox(
      width: 420,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: _chargeService,
            onChanged: (value) =>
                setState(() => _chargeService = value ?? true),
            title: const Text('Cobrar taxa de serviço'),
            subtitle: Text(
              widget.serviceFeePercent > 0
                  ? '${widget.serviceFeePercent.toStringAsFixed(2).replaceAll('.', ',')}'
                        ' · ${widget.money(widget.serviceFeeAmount)}'
                  : 'Desmarque para retirar a taxa deste pedido.',
            ),
          ),
          CheckboxListTile(
            contentPadding: EdgeInsets.zero,
            value: _includeCpf,
            onChanged: (value) => setState(() {
              _includeCpf = value ?? false;
              _cpfError = null;
              if (_includeCpf && _cpf.text.isEmpty) {
                _cpf.text = formatCpf(widget.customerCpf);
              }
            }),
            title: const Text('Incluir CPF na NFC-e'),
            subtitle: const Text(
              'O CPF será enviado como destinatário da nota fiscal.',
            ),
          ),
          // O CUPOM FICA JUNTO DO CPF, e não numa tela própria: o CPF é a
          // IDENTIDADE do cupom — é por ele que "compra única por cliente" e
          // "só para o grupo VIP" são conferidos. Separar os dois campos faria
          // o caixa digitar o cupom, ouvir "informe o CPF" e voltar.
          //
          // O código sobe no próprio fechamento. Uma chamada só, porque o
          // servidor precisa do CPF gravado ANTES de avaliar o cupom: aplicar
          // primeiro recusaria quem acabou de informar o CPF.
          TextField(
            key: const Key('coupon-code'),
            controller: _cupom,
            textCapitalization: TextCapitalization.characters,
            decoration: InputDecoration(
              labelText: 'Cupom de desconto (opcional)',
              hintText: 'NATAL10',
              prefixIcon: const Icon(Icons.local_activity_outlined),
              // O quanto está abatendo aparece aqui porque é a única pergunta
              // que o caixa faz depois de digitar: "entrou?".
              helperText: widget.couponDiscount > 0
                  ? 'Abatendo ${widget.money(widget.couponDiscount)} neste pedido.'
                  : 'Deixe em branco para não usar cupom.',
            ),
          ),
          if (_includeCpf)
            TextField(
              key: const Key('fiscal-cpf'),
              controller: _cpf,
              keyboardType: TextInputType.number,
              inputFormatters: [CpfInputFormatter()],
              decoration: InputDecoration(
                labelText: 'CPF para a NFC-e',
                hintText: '000.000.000-00',
                errorText: _cpfError,
                prefixIcon: const Icon(Icons.badge_outlined),
              ),
              onChanged: (_) {
                if (_cpfError != null) setState(() => _cpfError = null);
              },
            ),
        ],
      ),
    ),
    actions: [
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Voltar'),
      ),
      FilledButton.icon(
        onPressed: _confirm,
        icon: const Icon(Icons.payments_outlined),
        label: const Text('Ir para pagamento'),
      ),
    ],
  );
}
