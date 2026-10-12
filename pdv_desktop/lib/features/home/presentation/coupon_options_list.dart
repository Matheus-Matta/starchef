import 'package:flutter/material.dart';

/// A lista que abre sob o campo de cupom: "Nenhum" e os cupons vigentes.
///
/// O código em destaque e o nome da campanha embaixo: o caixa reconhece o
/// cupom pelo que o cliente falou ("o do Natal"), não só pelo código.
class CouponOptionsList extends StatelessWidget {
  const CouponOptionsList({
    super.key,
    required this.opcoes,
    required this.escolher,
  });

  final Iterable<Map<String, dynamic>> opcoes;
  final ValueChanged<Map<String, dynamic>> escolher;

  @override
  Widget build(BuildContext context) => Align(
    alignment: Alignment.topLeft,
    child: Material(
      elevation: 6,
      borderRadius: BorderRadius.circular(8),
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxHeight: 280, maxWidth: 420),
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.symmetric(vertical: 4),
          children: [
            for (final cupom in opcoes)
              ListTile(
                dense: true,
                title: Text(
                  '${cupom['code']}'.isEmpty ? 'Nenhum' : '${cupom['code']}',
                ),
                subtitle: '${cupom['name'] ?? ''}'.trim().isEmpty
                    ? null
                    : Text('${cupom['name']}'),
                onTap: () => escolher(cupom),
              ),
          ],
        ),
      ),
    ),
  );
}
