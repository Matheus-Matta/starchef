import 'package:flutter/material.dart';

import '../../../core/formatters/cnpj_formatter.dart';
import '../../../core/formatters/cpf_formatter.dart';
import '../../orders/presentation/order_discount_field.dart';
import 'campo_com_aplicar.dart';

/// Taxa de serviço, CPF/CNPJ da nota e desconto DENTRO da tela de pagamento.
///
/// Ficavam num modal antes dela: o caixa decidia a taxa e o documento sem ver
/// o total, e para mudar qualquer coisa depois tinha de voltar e refazer o
/// fechamento na frente do cliente. Aqui cada mudança vai ao servidor na hora
/// (o mixin `_PaymentAdjustSection` decide como) e o total se redesenha.
///
/// Widget próprio pelo mesmo motivo do `PaymentCouponInput`: é a parte que
/// responde à mão do operador, e a única que dá para verificar sem o PDV.
class PaymentAdjustments extends StatefulWidget {
  const PaymentAdjustments({
    super.key,
    required this.cobrarTaxa,
    required this.rotuloTaxa,
    required this.documento,
    required this.descontoCentavos,
    required this.maxDescontoCentavos,
    required this.busy,
    required this.bloqueado,
    required this.erro,
    required this.onTaxa,
    required this.onDocumento,
    required this.onDesconto,
  });

  final bool cobrarTaxa;

  /// "10% · R$ 12,36": quanto a chave tira ou põe, antes de mexer nela.
  final String rotuloTaxa;

  /// O CPF ou CNPJ que o pedido já leva (só dígitos). Vazio = nota sem nome.
  final String documento;
  final int descontoCentavos;

  /// O subtotal: dar a mercadoria inteira é o teto (o servidor recusa acima).
  final int maxDescontoCentavos;
  final bool busy;

  /// Já há pagamento lançado: mudar o total agora deixaria o recebido
  /// diferente da conta.
  final bool bloqueado;

  /// A recusa do servidor (senha do desconto, documento que ele não aceitou).
  final String erro;
  final ValueChanged<bool> onTaxa;

  /// Só os dígitos; vazio TIRA o documento da nota.
  final ValueChanged<String> onDocumento;
  final ValueChanged<int> onDesconto;

  @override
  State<PaymentAdjustments> createState() => _PaymentAdjustmentsState();
}

class _PaymentAdjustmentsState extends State<PaymentAdjustments> {
  late final _documento = TextEditingController(
    text: _formatar(widget.documento),
  );
  late final _desconto = TextEditingController(
    text: formatarCentavos(widget.descontoCentavos),
  );
  String _erroLocal = '';

  static String _formatar(String digitos) => digitos.length == 14
      ? formatCnpj(digitos)
      : digitos.length == 11
      ? formatCpf(digitos)
      : digitos;

  @override
  void didUpdateWidget(PaymentAdjustments antigo) {
    super.didUpdateWidget(antigo);
    // O servidor respondeu (ou outro pedido abriu): o campo mostra o que vale.
    if (antigo.documento != widget.documento) {
      _documento.text = _formatar(widget.documento);
    }
    if (antigo.descontoCentavos != widget.descontoCentavos) {
      _desconto.text = formatarCentavos(widget.descontoCentavos);
    }
  }

  @override
  void dispose() {
    _documento.dispose();
    _desconto.dispose();
    super.dispose();
  }

  void _aplicarDocumento() {
    final digitos = _documento.text.replaceAll(RegExp(r'\D'), '');
    final valido =
        digitos.isEmpty ||
        (digitos.length == 11 && isValidCpf(digitos)) ||
        (digitos.length == 14 && isValidCnpj(digitos));
    setState(
      () => _erroLocal = valido
          ? ''
          : 'CPF ou CNPJ inválido: confira os dígitos (CPF tem 11, CNPJ 14).',
    );
    if (valido && digitos != widget.documento) widget.onDocumento(digitos);
  }

  void _aplicarDesconto() {
    final centavos = centavosDigitados(_desconto.text);
    final acima = centavos > widget.maxDescontoCentavos;
    setState(
      () => _erroLocal = acima
          ? 'O desconto não pode ser maior que o subtotal do pedido.'
          : '',
    );
    if (!acima && centavos != widget.descontoCentavos) {
      widget.onDesconto(centavos);
    }
  }

  @override
  Widget build(BuildContext context) {
    final ativo = !widget.bloqueado && !widget.busy;
    final cores = Theme.of(context).colorScheme;
    final erro = _erroLocal.isNotEmpty ? _erroLocal : widget.erro;
    final dica = TextStyle(color: cores.onSurfaceVariant, fontSize: 12);
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        spacing: 8,
        children: [
          Row(
            children: [
              Switch(
                key: const Key('payment-service-fee'),
                value: widget.cobrarTaxa,
                onChanged: ativo ? widget.onTaxa : null,
              ),
              const SizedBox(width: 8),
              const Text('Taxa de serviço'),
              const SizedBox(width: 8),
              Flexible(
                child: Text(
                  widget.rotuloTaxa,
                  overflow: TextOverflow.ellipsis,
                  style: dica,
                ),
              ),
            ],
          ),
          Row(
            spacing: 10,
            children: [
              Expanded(
                child: CampoComAplicar(
                  chave: 'payment-document',
                  controle: _documento,
                  ativo: ativo,
                  rotulo: 'CPF ou CNPJ na nota',
                  icone: const Icon(Icons.badge_outlined, size: 18),
                  aplicar: _aplicarDocumento,
                ),
              ),
              SizedBox(
                width: 170,
                child: CampoComAplicar(
                  chave: 'payment-discount',
                  controle: _desconto,
                  ativo: ativo,
                  rotulo: 'Desconto',
                  prefixo: '- R\$ ',
                  formatador: CentavosFormatter(),
                  aplicar: _aplicarDesconto,
                ),
              ),
            ],
          ),
          if (widget.bloqueado)
            Text(
              'Remova os pagamentos lançados para mudar taxa, desconto ou '
              'documento.',
              style: dica,
            )
          else if (erro.isNotEmpty)
            Text(erro, style: TextStyle(color: cores.error, fontSize: 12)),
        ],
      ),
    );
  }
}
