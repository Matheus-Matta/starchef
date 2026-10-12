import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'payment_input_style.dart';

/// Um campo que só vale quando o operador APLICA: Enter ou o botão de check.
///
/// Mandar ao servidor a cada tecla recalcularia o pedido com um CPF pela
/// metade ou um desconto de R$ 0,05 a caminho de R$ 5,00. Usado pelo CPF/CNPJ
/// e pelo desconto da tela de pagamento (`payment_adjustments.dart`).
class CampoComAplicar extends StatelessWidget {
  const CampoComAplicar({
    super.key,
    required this.chave,
    required this.controle,
    required this.ativo,
    required this.rotulo,
    required this.aplicar,
    this.aplicado = false,
    this.remover,
    this.icone,
    this.prefixo,
    this.formatador,
  });

  final String chave;
  final TextEditingController controle;
  final bool ativo;
  final String rotulo;
  final VoidCallback aplicar;

  /// O valor do campo é o que o pedido já leva: o botão vira um X, porque o
  /// gesto que sobra é REMOVER — sem apagar o texto à mão.
  final bool aplicado;
  final VoidCallback? remover;
  final Widget? icone;
  final String? prefixo;

  /// Com formatador o campo é de valor: alinhado à direita, como no recibo.
  final TextInputFormatter? formatador;

  @override
  Widget build(BuildContext context) => TextField(
    key: Key(chave),
    controller: controle,
    enabled: ativo,
    textAlign: formatador == null ? TextAlign.start : TextAlign.right,
    keyboardType: TextInputType.number,
    textInputAction: TextInputAction.done,
    inputFormatters: [?formatador],
    decoration: campoDoPagamento(
      rotulo,
      prefixIcon: icone,
      prefixText: prefixo,
      suffixIcon: aplicado && remover != null
          ? botaoDoCampo(
              key: Key('$chave-remove'),
              icon: Icons.close_rounded,
              tooltip: 'Remover',
              onPressed: ativo ? remover : null,
            )
          : botaoDoCampo(
              icon: Icons.check_rounded,
              tooltip: 'Aplicar',
              onPressed: ativo ? aplicar : null,
            ),
    ),
    onSubmitted: (_) => aplicar(),
  );
}
