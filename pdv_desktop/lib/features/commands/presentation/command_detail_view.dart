import 'package:flutter/material.dart';

import '../../../core/formatters/value_formatters.dart';
import '../../home/presentation/product_catalog_panel.dart';
import 'command_cart_panel.dart';

/// O cartão ABERTO: catálogo à esquerda, carrinho à direita.
///
/// É o mesmo desenho da venda, e de propósito — quem alterna entre as duas
/// telas no turno não deve reaprender onde as coisas estão. O que muda são os
/// botões: aqui não existe pagamento.
///
/// Fica separado da página porque são dois assuntos: a página decide EM QUAL
/// das duas telas se está e conversa com o servidor; isto aqui só desenha.
class CommandDetailView extends StatelessWidget {
  const CommandDetailView({
    super.key,
    required this.comanda,
    required this.itens,
    required this.produtos,
    required this.todosOsProdutos,
    required this.categorias,
    required this.categoria,
    required this.termoDeProduto,
    required this.carregando,
    required this.enviando,
    required this.imprimindo,
    required this.onVoltar,
    required this.onBuscaDeProduto,
    required this.onCategoria,
    required this.onProduto,
    required this.onSendToKitchen,
    required this.onPrintReceipt,
    required this.onVoidItem,
  });

  final Map<String, dynamic>? comanda;
  final List<Map<String, dynamic>> itens;
  final List<Map<String, dynamic>> produtos;
  final List<Map<String, dynamic>> todosOsProdutos;
  final List<Map<String, dynamic>> categorias;
  final String? categoria;
  final String termoDeProduto;
  final bool carregando;
  final bool enviando;
  final bool imprimindo;
  final VoidCallback onVoltar;
  final ValueChanged<String> onBuscaDeProduto;
  final ValueChanged<String?> onCategoria;
  final ValueChanged<Map<String, dynamic>> onProduto;
  final VoidCallback onSendToKitchen;
  final VoidCallback onPrintReceipt;
  final ValueChanged<Map<String, dynamic>> onVoidItem;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton.icon(
              onPressed: onVoltar,
              icon: const Icon(Icons.arrow_back_rounded, size: 18),
              label: const Text('Todas as comandas'),
            ),
          ),
          const SizedBox(height: 8),
          Expanded(
            child: LayoutBuilder(
              builder: (context, constraints) {
                // As colunas cedem juntas em tela estreita. Larguras fixas
                // cabiam no monitor do balcão e estouravam no notebook do
                // escritório — e um estouro horizontal esconde justamente o
                // botão que fica na ponta.
                final largura = constraints.maxWidth;
                final larguraDoCarrinho = largura < 1000
                    ? 300.0
                    : (largura < 1300 ? 350.0 : 390.0);
                return Row(
                  children: [
                    Expanded(
                      child: ProductCatalogPanel(
                        products: produtos,
                        allProducts: todosOsProdutos,
                        categories: categorias,
                        selectedCategory: categoria,
                        search: termoDeProduto,
                        money: ValueFormatters.money,
                        onSearchChanged: (valor) => onBuscaDeProduto(valor),
                        onCategoryChanged: (valor) => onCategoria(valor),
                        onProductPressed: onProduto,
                      ),
                    ),
                    const SizedBox(width: 12),
                    SizedBox(
                      width: larguraDoCarrinho,
                      child: CommandCartPanel(
                        comanda: comanda,
                        itens: itens,
                        carregando: carregando,
                        enviando: enviando,
                        imprimindo: imprimindo,
                        onSendToKitchen: onSendToKitchen,
                        onPrintReceipt: onPrintReceipt,
                        onVoidItem: onVoidItem,
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}
