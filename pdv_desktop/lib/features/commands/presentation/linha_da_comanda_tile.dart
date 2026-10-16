import 'package:flutter/material.dart';

/// Uma linha da comanda como ela sai no papel: NOME, um traço para escrever e
/// três quadrados para marcar.
///
/// Os quadrados e o traço têm tamanho FIXO, e o nome ocupa só o que sobra,
/// cortado com reticências: um nome grande não pode empurrar os quadrados
/// para fora do lugar — no papel, é pelo alinhamento que o atendente acha a
/// coluna certa. `nome` nulo é a linha em branco: o traço ocupa a linha toda.
class LinhaDaComandaTile extends StatelessWidget {
  const LinhaDaComandaTile({
    super.key,
    required this.nome,
    this.onSubir,
    this.onDescer,
    required this.onRemover,
  });

  final String? nome;
  final VoidCallback? onSubir;
  final VoidCallback? onDescer;
  final VoidCallback onRemover;

  static const quadrados = 3;

  @override
  Widget build(BuildContext context) {
    final cor = Theme.of(context).colorScheme.onSurface;
    final traco = BoxDecoration(
      border: Border(bottom: BorderSide(color: cor, width: 1.2)),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        children: [
          if (nome != null) ...[
            Expanded(
              child: Text(
                nome!,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontWeight: FontWeight.w600),
              ),
            ),
            const SizedBox(width: 8),
            Container(width: 90, height: 18, decoration: traco),
          ] else
            Expanded(child: Container(height: 18, decoration: traco)),
          const SizedBox(width: 10),
          for (var i = 0; i < quadrados; i++)
            Container(
              width: 20,
              height: 20,
              margin: const EdgeInsets.only(right: 4),
              decoration: BoxDecoration(
                border: Border.all(color: cor, width: 1.2),
              ),
            ),
          const SizedBox(width: 8),
          IconButton(
            tooltip: 'Subir',
            onPressed: onSubir,
            icon: const Icon(Icons.arrow_upward_rounded, size: 18),
          ),
          IconButton(
            tooltip: 'Descer',
            onPressed: onDescer,
            icon: const Icon(Icons.arrow_downward_rounded, size: 18),
          ),
          IconButton(
            tooltip: 'Remover',
            onPressed: onRemover,
            icon: const Icon(Icons.close_rounded, size: 18),
          ),
        ],
      ),
    );
  }
}
