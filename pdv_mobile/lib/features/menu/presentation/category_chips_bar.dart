import 'package:flutter/material.dart';

/// As categorias do cardápio como chips tocáveis, acima da busca.
///
/// O garçom acha o produto tocando em "Bebidas" em vez de digitar com o
/// cliente esperando. "Todas" vem primeiro e devolve `null`.
class CategoryChipsBar extends StatelessWidget {
  const CategoryChipsBar({
    super.key,
    required this.categories,
    required this.selectedId,
    required this.onSelected,
  });

  final List<Map<String, dynamic>> categories;
  final String? selectedId;
  final ValueChanged<String?> onSelected;

  @override
  Widget build(BuildContext context) {
    final opcoes = <(String?, String)>[
      (null, 'Todas'),
      for (final categoria in categories)
        ('${categoria['id']}', '${categoria['name'] ?? ''}'),
    ];
    return SizedBox(
      height: 48,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        itemCount: opcoes.length,
        separatorBuilder: (_, _) => const SizedBox(width: 8),
        itemBuilder: (context, index) {
          final (id, nome) = opcoes[index];
          return ChoiceChip(
            label: Text(nome),
            selected: id == selectedId,
            onSelected: (_) => onSelected(id),
          );
        },
      ),
    );
  }
}
