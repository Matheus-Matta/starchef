import 'package:flutter/material.dart';

import 'app_error_host.dart';
import 'error_center.dart';
import 'notification_entry.dart';

/// O sino da barra superior: onde TODA notificação fica guardada.
///
/// Desde que só falha interrompe a tela, sucesso e aviso precisavam de um lugar
/// para existir — senão o operador perderia a confirmação de que a venda saiu,
/// e o único caminho seria adivinhar pelo estado do pedido.
///
/// O número no sino é "quantas chegaram desde que você olhou", não "quantas não
/// lidas uma a uma". A pergunta que o operador faz de relance é "apareceu coisa
/// nova?", e abrir a lista responde isso por inteiro.
class NotificationBell extends StatelessWidget {
  const NotificationBell({super.key});

  @override
  Widget build(BuildContext context) {
    final centro = ErrorCenterScope.of(context);
    final scheme = Theme.of(context).colorScheme;
    final novas = centro.unreadCount;

    return MenuAnchor(
      alignmentOffset: const Offset(-260, 6),
      menuChildren: [_PainelDeNotificacoes(centro: centro)],
      builder: (context, controller, _) => IconButton(
        tooltip: novas > 0
            ? '$novas ${novas == 1 ? 'notificação nova' : 'notificações novas'}'
            : 'Notificações',
        onPressed: () {
          if (controller.isOpen) {
            controller.close();
            return;
          }
          controller.open();
          // Marcar ao ABRIR, não ao fechar: se o operador abre e a tela some
          // por outro caminho (um diálogo, uma troca de aba), o que ele já viu
          // não pode voltar a contar como novo.
          centro.markAllSeen();
        },
        icon: Stack(
          clipBehavior: Clip.none,
          children: [
            const Icon(Icons.notifications_none, size: 24),
            if (novas > 0)
              Positioned(
                right: -4,
                top: -3,
                child: Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 5,
                    vertical: 1,
                  ),
                  constraints: const BoxConstraints(minWidth: 17),
                  decoration: BoxDecoration(
                    color: scheme.error,
                    borderRadius: BorderRadius.circular(9),
                  ),
                  child: Text(
                    // Acima de 99 o número deixa de ser informação e vira
                    // ruído que não cabe no desenho.
                    novas > 99 ? '99+' : '$novas',
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: scheme.onError,
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      height: 1.3,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _PainelDeNotificacoes extends StatelessWidget {
  const _PainelDeNotificacoes({required this.centro});

  final ErrorCenter centro;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final itens = centro.history;

    return SizedBox(
      width: 380,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 12, 8, 8),
            child: Row(
              children: [
                Text(
                  'Notificações',
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                ),
                const Spacer(),
                if (itens.isNotEmpty)
                  TextButton(
                    onPressed: centro.clearHistory,
                    child: const Text('Limpar'),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          if (itens.isEmpty)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 34, horizontal: 16),
              child: Text(
                'Nada por aqui ainda.',
                textAlign: TextAlign.center,
                style: TextStyle(color: scheme.onSurfaceVariant),
              ),
            )
          else
            SizedBox(
              // MenuAnchor mede a altura intrínseca dos filhos. Uma lista
              // shrinkWrap não fornece essa medida e lançava dezenas de
              // exceções de layout ao abrir o sino com notificações.
              // Altura explícita mantém o viewport virtualizado e rolável.
              height: itens.length < 5 ? itens.length * 84.0 : 420,
              child: ListView.separated(
                primary: false,
                padding: EdgeInsets.zero,
                itemCount: itens.length,
                separatorBuilder: (_, _) => const Divider(height: 1),
                itemBuilder: (context, indice) =>
                    NotificationEntry(item: itens[indice]),
              ),
            ),
        ],
      ),
    );
  }
}
