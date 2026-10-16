import 'package:flutter/material.dart';

/// Escolhe o produto de uma linha da comanda; devolve o id ou `null`.
///
/// Busca por nome, código interno ou EAN — o mesmo filtro da tela de venda.
/// Quem já está na lista não aparece: a mesma bebida duas vezes no papel só
/// divide as marcas em duas linhas.
class EscolherProdutoDaLinhaDialog extends StatefulWidget {
  const EscolherProdutoDaLinhaDialog({
    super.key,
    required this.produtos,
    this.jaEscolhidos = const {},
  });

  final List<Map<String, dynamic>> produtos;
  final Set<String> jaEscolhidos;

  @override
  State<EscolherProdutoDaLinhaDialog> createState() =>
      _EscolherProdutoDaLinhaDialogState();
}

class _EscolherProdutoDaLinhaDialogState
    extends State<EscolherProdutoDaLinhaDialog> {
  String _termo = '';

  List<Map<String, dynamic>> get _visiveis {
    final termo = _termo.trim().toLowerCase();
    return widget.produtos
        .where((p) => !widget.jaEscolhidos.contains('${p['id']}'))
        .where(
          (p) =>
              termo.isEmpty ||
              ['name', 'internal_code', 'ean'].any(
                (campo) => '${p[campo] ?? ''}'.toLowerCase().contains(termo),
              ),
        )
        .toList(growable: false);
  }

  @override
  Widget build(BuildContext context) {
    final visiveis = _visiveis;
    return AlertDialog(
      title: const Text('Adicionar item na comanda'),
      content: SizedBox(
        width: 460,
        height: 420,
        child: Column(
          children: [
            TextField(
              autofocus: true,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search_rounded),
                labelText: 'Buscar produto',
                isDense: true,
              ),
              onChanged: (valor) => setState(() => _termo = valor),
            ),
            const SizedBox(height: 8),
            Expanded(
              child: visiveis.isEmpty
                  ? const Center(child: Text('Nenhum produto encontrado.'))
                  : ListView.builder(
                      itemCount: visiveis.length,
                      itemBuilder: (_, i) => ListTile(
                        dense: true,
                        title: Text(
                          '${visiveis[i]['name'] ?? ''}',
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        onTap: () =>
                            Navigator.of(context).pop('${visiveis[i]['id']}'),
                      ),
                    ),
            ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
      ],
    );
  }
}
