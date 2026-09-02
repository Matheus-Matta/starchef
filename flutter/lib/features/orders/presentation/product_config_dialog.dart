import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/widgets/app_dialog.dart';

/// O que o operador escolheu para um produto: variação, adicionais,
/// quantidade/peso e observação — antes de o item entrar no pedido.
class ProductConfigResult {
  const ProductConfigResult({
    required this.quantity,
    required this.variationId,
    required this.addonIds,
    required this.customerNote,
  });

  /// Quantidade unitária ou peso em kg, conforme o cadastro do produto.
  final double quantity;
  final String? variationId;
  final List<String> addonIds;
  final String customerNote;
}

/// Diálogo de configuração de produto (variação, adicionais, quantidade e
/// observação), compartilhado entre o PDV padrão e a balança rápida — os
/// dois lançam item em um pedido e precisam da mesma pergunta ao operador.
///
/// Devolve `null` se cancelado. A altura é limitada e o conteúdo rola: numa
/// janela baixa ou com cardápio de muitos adicionais, o diálogo nunca cresce
/// além do que a tela permite.
Future<ProductConfigResult?> showProductConfigDialog(
  BuildContext context,
  Map<String, dynamic> product, {
  Stream<void>? repeatedScans,
}) async {
  final soldByWeight = isProductSoldByWeight(product);
  final variations = (product['variations'] as List? ?? [])
      .cast<Map<String, dynamic>>()
      .where((item) => item['is_active'] != false)
      .toList();
  final addons = (product['addons'] as List? ?? [])
      .cast<Map<String, dynamic>>()
      .where((item) => item['is_active'] != false)
      .toList();
  String? variation;
  final selectedAddons = <String>{};
  var quantity = soldByWeight ? 0.0 : 1.0;
  var customerNote = '';
  StreamSubscription<void>? repeats;
  final accepted = await showDialog<bool>(
    context: context,
    builder: (context) => StatefulBuilder(
      builder: (context, update) {
        // Ler o mesmo produto de novo com o modal aberto soma quantidade aqui,
        // em vez de abrir um segundo modal por cima do primeiro. É o que
        // permite bipar cinco unidades em sequência sem tocar no teclado.
        repeats ??= repeatedScans?.listen((_) {
          if (soldByWeight) return;
          update(() => quantity += 1);
        });
        final size = MediaQuery.sizeOf(context);
        final maxHeight = (size.height * .75).clamp(320.0, 620.0);
        // Mesmo 560-720 ainda ficava apertado para nomes de adicional
        // mais longos e o preço do lado — segue quebrando linha à toa.
        // Uma fração maior da largura da janela resolve sem tomar a tela
        // inteira numa janela pequena.
        final maxWidth = (size.width * .62).clamp(680.0, 900.0);
        // O que impede "Adicionar" — a mesma regra para o botão e para o
        // Enter, senão o teclado poderia lançar um item que o botão recusa.
        final blocked =
            (product['requires_variation'] == true && variation == null) ||
            (soldByWeight && quantity <= 0);
        void confirm() {
          if (blocked) return;
          Navigator.pop(context, true);
        }

        // Enter confirma. O balcão trabalha com as duas mãos ocupadas — uma no
        // leitor, outra no produto —, e obrigar a levar a mão ao mouse para
        // fechar um modal que só tinha uma escolha marcada era o gesto mais
        // caro da venda. A observação é multilinha e trata o Enter dela mesma
        // (quebra de linha), então este atalho não a atrapalha: só recebe a
        // tecla quando ninguém abaixo a consumiu.
        return CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.enter): confirm,
            const SingleActivator(LogicalKeyboardKey.numpadEnter): confirm,
          },
          // O atalho só recebe a tecla se o foco estiver DENTRO dele: sem este
          // nó, o foco fica no escopo da rota do diálogo — um ancestral — e o
          // Enter passava por cima sem tocar em nada. Não toma o foco quando o
          // campo de peso já se autofoca, para não haver dois autofocus
          // disputando o mesmo escopo.
          child: Focus(
            autofocus: !(soldByWeight && variations.isEmpty && addons.isEmpty),
            child: AppDialog(
              title: Text('${product['name']}'),
              content: ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: maxWidth,
                  maxHeight: maxHeight,
                ),
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      if (variations.isNotEmpty) ...[
                        const Text(
                          'Variação',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        ...variations.map((item) {
                          final id = '${item['id']}';
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            leading: Icon(
                              variation == id
                                  ? Icons.radio_button_checked
                                  : Icons.radio_button_off,
                            ),
                            title: Text(
                              '${item['name']}  + ${_money(item['price_delta'])}',
                            ),
                            onTap: () => update(() => variation = id),
                          );
                        }),
                      ],
                      if (addons.isNotEmpty) ...[
                        const SizedBox(height: 8),
                        const Text(
                          'Adicionais',
                          style: TextStyle(fontWeight: FontWeight.w700),
                        ),
                        ...addons.map(
                          (item) => CheckboxListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text(
                              '${item['name']}  + ${_money(item['price'])}',
                            ),
                            value: selectedAddons.contains('${item['id']}'),
                            onChanged: (checked) => update(
                              () => checked == true
                                  ? selectedAddons.add('${item['id']}')
                                  : selectedAddons.remove('${item['id']}'),
                            ),
                          ),
                        ),
                      ],
                      const SizedBox(height: 12),
                      if (soldByWeight)
                        TextField(
                          key: const Key('product-weight'),
                          autofocus: variations.isEmpty && addons.isEmpty,
                          keyboardType: const TextInputType.numberWithOptions(
                            decimal: true,
                          ),
                          decoration: const InputDecoration(
                            labelText: 'Peso',
                            hintText: '0,000',
                            suffixText: 'kg',
                            prefixIcon: Icon(Icons.scale_outlined),
                          ),
                          onChanged: (value) => update(
                            () => quantity =
                                double.tryParse(value.replaceAll(',', '.')) ??
                                0,
                          ),
                        )
                      else
                        LayoutBuilder(
                          builder: (context, constraints) {
                            final controls = Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                IconButton.filledTonal(
                                  onPressed: quantity > 1
                                      ? () => update(() => quantity--)
                                      : null,
                                  icon: const Icon(Icons.remove),
                                ),
                                Padding(
                                  padding: const EdgeInsets.symmetric(
                                    horizontal: 12,
                                  ),
                                  child: Text(
                                    '${quantity.round()}',
                                    style: const TextStyle(
                                      fontSize: 18,
                                      fontWeight: FontWeight.w800,
                                    ),
                                  ),
                                ),
                                IconButton.filled(
                                  onPressed: () => update(() => quantity++),
                                  icon: const Icon(Icons.add),
                                ),
                              ],
                            );
                            if (constraints.maxWidth < 340) {
                              return Column(
                                crossAxisAlignment: CrossAxisAlignment.stretch,
                                children: [
                                  const Text(
                                    'Quantidade',
                                    style: TextStyle(
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                  const SizedBox(height: 8),
                                  Align(
                                    alignment: Alignment.centerRight,
                                    child: controls,
                                  ),
                                ],
                              );
                            }
                            return Row(
                              children: [
                                const Text(
                                  'Quantidade',
                                  style: TextStyle(fontWeight: FontWeight.w700),
                                ),
                                const Spacer(),
                                controls,
                              ],
                            );
                          },
                        ),
                      const SizedBox(height: 12),
                      TextField(
                        maxLines: 2,
                        decoration: const InputDecoration(
                          labelText: 'Observação',
                          hintText: 'Ex.: sem cebola',
                        ),
                        onChanged: (value) => customerNote = value,
                      ),
                    ],
                  ),
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: blocked ? null : confirm,
                  child: const Text('Adicionar (Enter)'),
                ),
              ],
            ),
          ),
        );
      },
    ),
  );
  await repeats?.cancel();
  if (accepted != true) return null;
  return ProductConfigResult(
    quantity: quantity,
    variationId: variation,
    addonIds: selectedAddons.toList(),
    customerNote: customerNote.trim(),
  );
}

/// Aceita tanto o contrato atual (`pricing_unit=kg`) quanto payloads locais
/// antigos que traziam apenas `is_weighed=true`.
bool isProductSoldByWeight(Map<String, dynamic> product) =>
    '${product['pricing_unit'] ?? ''}'.toLowerCase() == 'kg' ||
    product['is_weighed'] == true;

String _money(dynamic value) {
  final number = value is num ? value : num.tryParse('$value') ?? 0;
  return 'R\$ ${number.toStringAsFixed(2).replaceAll('.', ',')}';
}
