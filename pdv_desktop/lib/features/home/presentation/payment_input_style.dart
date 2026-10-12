import 'package:flutter/material.dart';

/// O campo da tela de pagamento: cupom, forma, referência, CPF/CNPJ, desconto.
///
/// Altura, borda e espaçamento vêm do TEMA (`AppTheme`, 40 px) — este ajudante
/// só dá o rótulo e os ícones. O cupom tinha um tamanho próprio, "compacto de
/// propósito", e destoava da forma de pagamento ao lado
/// (a fonte real, Segoe UI, mostra a diferença; a dos testes, não).
InputDecoration campoDoPagamento(
  String rotulo, {
  Widget? prefixIcon,
  String? prefixText,
  Widget? suffixIcon,
  String? hintText,
}) => InputDecoration(
  // ALTURA FIXA para todos: o tema dá uma altura mínima só para a caixa do
  // ÍCONE, e o campo com ícone (cupom, CPF, desconto) ficava mais alto que o
  // sem ícone (forma, referência) — visto com a fonte real, não nos testes.
  constraints: const BoxConstraints.tightFor(height: alturaDoCampo),
  contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
  prefixIconConstraints: const BoxConstraints(minWidth: 36),
  suffixIconConstraints: const BoxConstraints(minWidth: 36),
  labelText: rotulo,
  hintText: hintText,
  prefixIcon: prefixIcon,
  prefixText: prefixText,
  suffixIcon: suffixIcon,
);

/// A altura dos campos da tela de pagamento.
const alturaDoCampo = 44.0;

/// O botão DENTRO do campo (aplicar, remover): pequeno, para não esticá-lo.
Widget botaoDoCampo({
  required IconData icon,
  required String tooltip,
  required VoidCallback? onPressed,
  Key? key,
}) => IconButton(
  key: key,
  tooltip: tooltip,
  onPressed: onPressed,
  icon: Icon(icon, size: 18),
  padding: EdgeInsets.zero,
  visualDensity: VisualDensity.compact,
);
