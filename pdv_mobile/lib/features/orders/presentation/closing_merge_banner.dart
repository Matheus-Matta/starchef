import 'package:flutter/material.dart';

import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/shadcn_layout.dart';

/// A comanda está numa conta agrupada que o caixa está fechando agora.
///
/// O garçom precisa ver isto ANTES de escolher um produto, não depois de o
/// servidor recusar o lançamento. O defeito que o aviso evita é o mais caro
/// deste fluxo: o caixa lê a conta em voz alta para o cliente enquanto o
/// garçom lança mais um item — e a comida sai sem ninguém cobrar.
///
/// O garçom não fecha conta: aqui não há botão para desfazer nem para
/// confirmar. O aviso só diz o que está acontecendo e a quem recorrer.
class ClosingMergeBanner extends StatelessWidget {
  const ClosingMergeBanner({super.key, required this.merge});

  /// O objeto `closing_merge` do pedido, como o backend o devolve, ou `null`.
  final Object? merge;

  /// "Em fechamento" é DERIVADO do backend, nunca um estado gravado na
  /// comanda — um estado a mais seria mais uma coisa a sincronizar e divergir.
  static bool isClosing(Map<String, dynamic>? order) {
    final merge = order?['closing_merge'];
    if (merge is! Map) return false;
    return merge['role'] == 'source';
  }

  @override
  Widget build(BuildContext context) {
    if (merge is! Map || (merge as Map)['role'] != 'source') {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: AppTheme.bannerPadding,
      child: const AppNotice(
        tone: AppNoticeTone.warning,
        icon: Icons.point_of_sale_outlined,
        message:
            'Esta comanda está em fechamento numa conta agrupada. Novos '
            'lançamentos ficam bloqueados até o caixa concluir ou desfazer a '
            'conta.',
      ),
    );
  }
}
