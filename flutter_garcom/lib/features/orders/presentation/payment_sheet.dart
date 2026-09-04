import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/theme/app_theme.dart';
import 'order_formatters.dart';

/// O que o garçom escolheu receber.
class PaymentRequest {
  const PaymentRequest({
    required this.methodId,
    required this.methodName,
    required this.amount,
    this.reference = '',
  });

  final String methodId;
  final String methodName;

  /// Valor em texto, com ponto decimal — o formato que a API aceita.
  final String amount;
  final String reference;
}

/// Recebimento no aparelho do garçom, operando como caixa secundário.
///
/// A conta é a mesma do PDV: total menos o que já foi recebido. O que muda é
/// quem executa — o aparelho não fala com a nuvem, ele entrega a operação ao
/// Caixa Principal, que grava no SQLite dele e sincroniza depois (§8, §9).
///
/// Dinheiro só aparece quando existe um caixa aberto: um recebimento em
/// espécie precisa entrar em alguma sessão, e quem sabe qual está aberta é o
/// principal.
Future<PaymentRequest?> showPaymentSheet(
  BuildContext context, {
  required List<Map<String, dynamic>> methods,
  required double remaining,
  required bool cashRegisterOpen,
}) {
  return showModalBottomSheet<PaymentRequest>(
    context: context,
    isScrollControlled: true,
    showDragHandle: true,
    builder: (context) => Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: _PaymentSheet(
        methods: methods,
        remaining: remaining,
        cashRegisterOpen: cashRegisterOpen,
      ),
    ),
  );
}

class _PaymentSheet extends StatefulWidget {
  const _PaymentSheet({
    required this.methods,
    required this.remaining,
    required this.cashRegisterOpen,
  });

  final List<Map<String, dynamic>> methods;
  final double remaining;
  final bool cashRegisterOpen;

  @override
  State<_PaymentSheet> createState() => _PaymentSheetState();
}

class _PaymentSheetState extends State<_PaymentSheet> {
  late final TextEditingController _amount = TextEditingController(
    text: widget.remaining.toStringAsFixed(2).replaceAll('.', ','),
  );
  final _reference = TextEditingController();
  String? _methodId;

  List<Map<String, dynamic>> get _available => widget.methods
      .where(
        (method) =>
            widget.cashRegisterOpen || '${method['method_type']}' != 'cash',
      )
      .toList();

  Map<String, dynamic>? get _method => _available
      .cast<Map<String, dynamic>?>()
      .firstWhere((item) => '${item?['id']}' == _methodId, orElse: () => null);

  double get _typed => amount(_amount.text);

  @override
  void dispose() {
    _amount.dispose();
    _reference.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final method = _method;
    final isCash = '${method?['method_type']}' == 'cash';
    // Só dinheiro aceita valor acima do que falta — é o troco. Nas outras
    // formas, cobrar a mais não tem como ser devolvido pelo aparelho.
    final excessive = !isCash && _typed > widget.remaining + 0.009;
    final change = isCash && _typed > widget.remaining
        ? _typed - widget.remaining
        : 0.0;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(20, 0, 20, 20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Receber',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: 4),
            Text(
              'Falta ${money(widget.remaining)}',
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 16),
            if (_available.isEmpty)
              Text(
                'Nenhuma forma de pagamento disponível. Sem caixa aberto, '
                'o recebimento em dinheiro precisa ser feito no PDV.',
                style: TextStyle(color: scheme.error),
              )
            else ...[
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final item in _available)
                    ChoiceChip(
                      selected: '${item['id']}' == _methodId,
                      label: Text('${item['name']}'),
                      onSelected: (_) =>
                          setState(() => _methodId = '${item['id']}'),
                    ),
                ],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _amount,
                keyboardType: const TextInputType.numberWithOptions(
                  decimal: true,
                ),
                inputFormatters: [
                  FilteringTextInputFormatter.allow(RegExp(r'[0-9,.]')),
                ],
                decoration: const InputDecoration(
                  labelText: 'Valor recebido',
                  prefixText: r'R$ ',
                ),
                onChanged: (_) => setState(() {}),
              ),
              if (!isCash) ...[
                const SizedBox(height: 12),
                TextField(
                  controller: _reference,
                  decoration: const InputDecoration(
                    labelText: 'Referência (NSU, autorização)',
                  ),
                ),
              ],
              if (change > 0) ...[
                const SizedBox(height: 12),
                Text(
                  'Troco: ${money(change)}',
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
              ],
              if (excessive) ...[
                const SizedBox(height: 12),
                Text(
                  'Somente dinheiro pode receber mais do que falta.',
                  style: TextStyle(color: scheme.error),
                ),
              ],
            ],
            const SizedBox(height: 20),
            ShadButton(
              height: AppTheme.controlHeight,
              enabled: method != null && _typed > 0 && !excessive,
              onPressed: method == null || _typed <= 0 || excessive
                  ? null
                  : () => Navigator.pop(
                      context,
                      PaymentRequest(
                        methodId: '${method['id']}',
                        methodName: '${method['name']}',
                        // A API recebe decimal com ponto; o operador digita
                        // com vírgula.
                        amount: _typed.toStringAsFixed(2),
                        reference: _reference.text.trim(),
                      ),
                    ),
              child: Text('Receber ${money(_typed)}'),
            ),
          ],
        ),
      ),
    );
  }
}
