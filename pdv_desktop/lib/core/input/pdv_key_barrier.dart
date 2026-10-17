import 'package:flutter/widgets.dart';

import 'pdv_input_router.dart';

/// Impede que uma tecla já usada pelo roteador do PDV chegue também ao
/// widget com foco.
///
/// O roteador escuta pelo `HardwareKeyboard`, e no Flutter isso NÃO segura a
/// tecla: ela segue para o foco do mesmo jeito. Com o sino de notificações
/// focado pelo Tab, um Enter na tela de pagamento registrava o recebimento E
/// abria as notificações. Esta barreira fica acima da tela do PDV; a tecla
/// sobe do botão focado até os atalhos do aplicativo (Enter = ativar) e para
/// aqui quando o roteador já a usou.
///
/// Campo de texto não é afetado: com o cursor num campo o roteador não usa
/// Enter nem setas, então elas continuam chegando a ele.
class PdvKeyBarrier extends StatelessWidget {
  const PdvKeyBarrier({super.key, required this.router, required this.child});

  final PdvInputRouter router;
  final Widget child;

  @override
  Widget build(BuildContext context) => Focus(
    canRequestFocus: false,
    skipTraversal: true,
    onKeyEvent: (_, event) => router.consumedByRouter(event)
        ? KeyEventResult.handled
        : KeyEventResult.ignored,
    child: child,
  );
}
