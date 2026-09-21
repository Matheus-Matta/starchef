import 'package:flutter/material.dart';

import '../../../core/network/cloud_fallback.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/app_feedback.dart';

/// Aviso de que quem está atendendo é a NUVEM, não o servidor da loja.
///
/// Não é um detalhe de rede — é uma mudança de ONDE o lançamento está sendo
/// gravado. Enquanto durar:
///
/// * o que o garçom lançar vive na nuvem até a loja voltar;
/// * outro aparelho que ainda alcance a loja enxerga um salão DIFERENTE;
/// * nota fiscal e caixa não funcionam, porque não desviam de propósito — dois
///   emissores de número de nota, ou duas sessões no mesmo turno, não se
///   resolvem com sincronização.
///
/// É irmão do [StaleDataBanner], e a diferença entre os dois importa: aquele
/// avisa que a tela mostra um RETRATO velho; este avisa que a escrita está
/// indo para OUTRO servidor. O primeiro é sobre o que se lê; o segundo, sobre
/// onde a venda fica.
class CloudModeBanner extends StatelessWidget {
  const CloudModeBanner({super.key, required this.origin});

  final ServerOrigin origin;

  @override
  Widget build(BuildContext context) {
    if (origin != ServerOrigin.nuvem) return const SizedBox.shrink();
    return Padding(
      padding: AppTheme.bannerPadding,
      child: const AppNotice(
        tone: AppNoticeTone.warning,
        icon: Icons.cloud_outlined,
        message:
            'Atendendo pela NUVEM: o servidor da loja não está respondendo. '
            'O que você lançar é gravado lá e desce quando ele voltar. Nota '
            'fiscal e caixa ficam indisponíveis até então.',
      ),
    );
  }
}
