import 'package:flutter/material.dart';

/// A faixa de "estamos na nuvem", atravessada no topo da tela.
///
/// O selo de conexão na barra já muda de cor, mas um selo é discreto — e isto
/// aqui não é um detalhe de rede, é uma mudança de ONDE a venda está sendo
/// gravada. Enquanto durar:
///
/// * o que o operador lançar vive na nuvem até a loja voltar;
/// * outro terminal que ainda alcance a loja enxerga um salão DIFERENTE;
/// * nota fiscal e caixa não funcionam, porque não desviam de propósito —
///   dois emissores de número de nota, ou duas sessões no mesmo turno, não se
///   resolvem com sincronização.
///
/// O operador precisa saber os três sem procurar. Uma faixa que ocupa a
/// largura da tela é o que garante isso; a alternativa é ele descobrir quando
/// a nota não sair.
class PdvCloudBanner extends StatelessWidget {
  const PdvCloudBanner({super.key, required this.visible});

  /// A loja está fora e quem está atendendo é a nuvem.
  final bool visible;

  @override
  Widget build(BuildContext context) {
    if (!visible) return const SizedBox.shrink();
    return Material(
      color: const Color(0xFF1D4ED8),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
        child: Row(
          children: [
            const Icon(Icons.cloud_outlined, size: 17, color: Colors.white),
            const SizedBox(width: 9),
            const Expanded(
              child: Text(
                'O servidor da loja não está respondendo — as vendas estão '
                'sendo gravadas na nuvem e descem quando ele voltar. '
                'Nota fiscal e caixa ficam indisponíveis até lá.',
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
