import 'package:flutter/material.dart';

/// O campo de cupom da tela de pagamento: digitar, aplicar, trocar, retirar.
///
/// Widget próprio porque é a parte que RESPONDE ao operador — e a única do
/// controle de cupom que dá para verificar sem montar o PDV inteiro. A regra de
/// quando chamar o servidor e o que fazer com a resposta fica no mixin; aqui só
/// vive o que a mão faz.
///
/// TROCAR E RETIRAR são dois botões, e não um. São gestos diferentes com a mesma
/// urgência: o cliente trouxe outro cupom, ou desistiu deste. Um botão só
/// obrigaria o operador a apagar o campo para descobrir que aquilo também
/// removia.
class PaymentCouponInput extends StatelessWidget {
  const PaymentCouponInput({
    super.key,
    required this.controller,
    required this.applied,
    required this.busy,
    required this.error,
    required this.onSubmit,
    required this.onRemove,
  });

  final TextEditingController controller;

  /// O código que o pedido já carrega. Vazio = nenhum cupom aplicado.
  final String applied;
  final bool busy;
  final String error;

  /// Aplicar ou trocar — o servidor trata os dois do mesmo jeito.
  final ValueChanged<String> onSubmit;
  final VoidCallback onRemove;

  bool get _temCupom => applied.trim().isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final cores = Theme.of(context).colorScheme;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: TextField(
            key: const Key('payment-coupon-code'),
            controller: controller,
            enabled: !busy,
            textCapitalization: TextCapitalization.characters,
            onSubmitted: onSubmit,
            decoration: InputDecoration(
              isDense: true,
              labelText: 'Cupom',
              hintText: 'NATAL10',
              errorText: error.isEmpty ? null : error,
              // As frases do servidor explicam o MOTIVO, e cortá-las numa linha
              // deixaria "Este CPF já usou este…" — que não resolve nada para
              // quem está atendendo.
              errorMaxLines: 3,
              prefixIcon: const Icon(Icons.local_activity_outlined, size: 18),
            ),
          ),
        ),
        const SizedBox(width: 6),
        Padding(
          padding: const EdgeInsets.only(top: 2),
          child: busy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : Row(
                  children: [
                    // O BOTAO OUVE O CONTROLADOR.
                    //
                    // Sem isto ele nasce desabilitado (campo vazio) e nada o
                    // reabilita: quem digita o codigo nao dispara `setState` de
                    // ninguem, e o operador ficava olhando um botao morto com o
                    // cupom escrito na tela. Foi o defeito que o teste achou.
                    ValueListenableBuilder<TextEditingValue>(
                      valueListenable: controller,
                      builder: (context, valor, _) => FilledButton(
                        key: const Key('payment-coupon-apply'),
                        onPressed: valor.text.trim().isEmpty
                            ? null
                            : () => onSubmit(valor.text.trim()),
                        child: Text(_temCupom ? 'Trocar' : 'Aplicar'),
                      ),
                    ),
                    if (_temCupom) ...[
                      const SizedBox(width: 6),
                      OutlinedButton(
                        key: const Key('payment-coupon-remove'),
                        onPressed: onRemove,
                        style: OutlinedButton.styleFrom(foregroundColor: cores.error),
                        child: const Text('Retirar'),
                      ),
                    ],
                  ],
                ),
        ),
      ],
    );
  }
}
