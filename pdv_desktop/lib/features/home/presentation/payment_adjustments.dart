import 'package:flutter/material.dart';

import '../../../core/formatters/documento_fiscal.dart';
import '../../orders/presentation/order_discount_field.dart';
import 'campo_com_aplicar.dart';

/// Taxa de serviço, CPF/CNPJ da nota e desconto DENTRO da tela de pagamento.
///
/// Ficavam num modal antes dela, decididos sem ver o total. Cada mudança vai
/// ao servidor na hora (`_PaymentAdjustSection`) e o total se redesenha.
class PaymentAdjustments extends StatefulWidget {
  const PaymentAdjustments({
    super.key,
    required this.cobrarTaxa,
    required this.rotuloTaxa,
    required this.documento,
    required this.documentoControle,
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
  final TextEditingController documentoControle; // lido ao pagar
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
  TextEditingController get _documento => widget.documentoControle;
  late final _desconto = TextEditingController(
    text: formatarCentavos(widget.descontoCentavos),
  );
  String _erroLocal = '';

  @override
  void initState() {
    super.initState();
    _documento.text = documentoFormatado(widget.documento);
    // O botão do campo (aplicar ou remover) depende do que está digitado.
    _documento.addListener(_redesenhar);
    _desconto.addListener(_redesenhar);
  }

  void _redesenhar() => setState(() {});

  bool get _documentoAplicado =>
      widget.documento.isNotEmpty &&
      documentoDigitos(_documento.text) == widget.documento;

  bool get _descontoAplicado =>
      widget.descontoCentavos > 0 &&
      centavosDigitados(_desconto.text) == widget.descontoCentavos;

  @override
  void didUpdateWidget(PaymentAdjustments antigo) {
    super.didUpdateWidget(antigo);
    // O servidor respondeu (ou outro pedido abriu): o campo mostra o que vale.
    if (antigo.documento != widget.documento) {
      _documento.text = documentoFormatado(widget.documento);
      _erroLocal = ''; // o erro de antes falava de outro texto
    }
    if (antigo.descontoCentavos != widget.descontoCentavos) {
      _desconto.text = formatarCentavos(widget.descontoCentavos);
    }
  }

  @override
  void dispose() {
    _documento.removeListener(_redesenhar); // o controle é de quem monta
    _desconto.dispose();
    super.dispose();
  }

  void _aplicarDocumento() {
    final digitos = documentoDigitos(_documento.text);
    final valido = documentoValido(digitos);
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
    // EMPILHADOS, abaixo do teclado: taxa, documento e desconto mexem no
    // valor que o teclado está cobrando, e é ali que o caixa está olhando.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      // O rótulo do campo flutua ACIMA da borda: com 6 px ele encostava
      // na linha de cima.
      spacing: 12,
      children: [
        Row(
          children: [
            const Text('Taxa de serviço'),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                widget.rotuloTaxa,
                overflow: TextOverflow.ellipsis,
                style: dica,
              ),
            ),
            // PEQUENA: no tamanho padrão a chave era maior que os campos e
            // as teclas ao redor, e puxava o olho para o que menos muda.
            SizedBox(
              height: 24,
              child: FittedBox(
                child: Switch(
                  key: const Key('payment-service-fee'),
                  value: widget.cobrarTaxa,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                  onChanged: ativo ? widget.onTaxa : null,
                ),
              ),
            ),
          ],
        ),
        CampoComAplicar(
          chave: 'payment-document',
          controle: _documento,
          ativo: ativo,
          rotulo: 'CPF ou CNPJ na nota',
          icone: const Icon(Icons.badge_outlined, size: 18),
          aplicar: _aplicarDocumento,
          aplicado: _documentoAplicado,
          remover: () => widget.onDocumento(''),
        ),
        CampoComAplicar(
          chave: 'payment-discount',
          controle: _desconto,
          ativo: ativo,
          rotulo: 'Desconto',
          prefixo: '- R\$ ',
          formatador: CentavosFormatter(),
          aplicar: _aplicarDesconto,
          aplicado: _descontoAplicado,
          remover: () => widget.onDesconto(0),
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
    );
  }
}
