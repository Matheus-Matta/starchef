import 'package:flutter/material.dart';

import 'destaque_da_grade.dart';
import 'product_card_metrics.dart';
import 'product_catalog_tile.dart';

/// A grade de produtos da venda, com o produto em destaque das setas.
///
/// Informa quantas colunas desenha ([onColunas]): é o tamanho do passo de
/// ↑ ↓ (`destaque_da_grade.dart`). E rola até o destacado quando ele sai da
/// área visível — destacar um produto que ninguém vê não serve para nada.
class GradeDeProdutos extends StatelessWidget {
  const GradeDeProdutos({
    super.key,
    required this.products,
    required this.money,
    required this.onProductPressed,
    this.destacado,
    this.onColunas,
  });

  final List<Map<String, dynamic>> products;
  final String Function(dynamic) money;
  final ValueChanged<Map<String, dynamic>> onProductPressed;
  final int? destacado;
  final ValueChanged<int>? onColunas;

  static const _respiro = 8.0;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      onColunas?.call(colunasDaGrade(constraints.maxWidth - _respiro * 2));
      return GridView.builder(
        padding: const EdgeInsets.all(_respiro),
        keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
        gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
          maxCrossAxisExtent: ProductCardMetrics.maxCardWidth,
          mainAxisExtent: ProductCardMetrics.cardHeight,
          crossAxisSpacing: ProductCardMetrics.spacing,
          mainAxisSpacing: ProductCardMetrics.spacing,
        ),
        itemCount: products.length,
        itemBuilder: (_, index) {
          final noDestaque = index == destacado;
          // O embrulho existe SEMPRE: trocar a árvore só no destacado
          // recriava o cartão a cada seta, e a imagem piscava recarregando.
          return _Revelar(
            ativo: noDestaque,
            child: ProductCatalogTile(
              product: products[index],
              money: money,
              destacado: noDestaque,
              onPressed: () => onProductPressed(products[index]),
            ),
          );
        },
      );
    },
  );
}

/// Rola a grade até este cartão quando ele passa a ser o destacado.
class _Revelar extends StatefulWidget {
  const _Revelar({required this.ativo, required this.child});

  final bool ativo;
  final Widget child;

  @override
  State<_Revelar> createState() => _RevelarState();
}

class _RevelarState extends State<_Revelar> {
  @override
  void initState() {
    super.initState();
    if (widget.ativo) _revelar();
  }

  @override
  void didUpdateWidget(_Revelar antigo) {
    super.didUpdateWidget(antigo);
    if (widget.ativo && !antigo.ativo) _revelar();
  }

  void _revelar() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      Scrollable.ensureVisible(
        context,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
        duration: const Duration(milliseconds: 120),
      );
      Scrollable.ensureVisible(
        context,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtStart,
        duration: const Duration(milliseconds: 120),
      );
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}
