import 'package:flutter/material.dart';

import '../../../core/input/pdv_shortcuts.dart';
import 'pdv_navigation_rail_button.dart';
import 'pdv_navigation_shell.dart';

/// Navegação fixa do posto de venda. A largura nunca muda: o catálogo não
/// salta quando o operador troca de tela e os destinos permanecem no mesmo
/// lugar durante todo o turno.
///
/// TODO destino de [PdvDestination] precisa de uma entrada aqui — é o único
/// caminho até as telas. `PdvSidebar`, em `pdv_navigation_shell.dart`, tem
/// uma lista parecida e não é usada por ninguém: foi acreditando nela que o
/// "Clientes" passou despercebido como se estivesse no ar.
class PdvNavigationRail extends StatelessWidget {
  const PdvNavigationRail({
    super.key,
    required this.selected,
    required this.onSelected,
    required this.showOrders,
    required this.showFinance,
  });

  final PdvDestination selected;
  final ValueChanged<PdvDestination> onSelected;
  final bool showOrders;
  final bool showFinance;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final entries = <RailEntry>[
      // "Venda", igual à barra lateral expandida: o destino é o mesmo, e o
      // trilho e a barra precisam chamá-lo pelo mesmo nome.
      const RailEntry(PdvDestination.sale, 'Venda', Icons.grid_view_rounded),
      if (showOrders)
        const RailEntry(
          PdvDestination.orders,
          'Pedidos',
          Icons.receipt_long_outlined,
        ),
      const RailEntry(
        PdvDestination.tables,
        'Mesas',
        Icons.table_restaurant_outlined,
      ),
      const RailEntry(
        PdvDestination.commands,
        'Comandas',
        Icons.qr_code_2_outlined,
      ),
      // CLIENTES FALTAVA AQUI. O destino existia no enum, `_navigateTo` o
      // tratava e a tela era desenhada por `flowStep == 'customers'` — só não
      // havia botão nenhum que o selecionasse, e o cadastro de cliente ficava
      // inalcançável no desktop inteiro.
      const RailEntry(
        PdvDestination.customers,
        'Clientes',
        Icons.people_outline,
      ),
      if (showFinance)
        const RailEntry(
          PdvDestination.finance,
          'Caixa',
          Icons.account_balance_wallet_outlined,
        ),
      const RailEntry(PdvDestination.scale, 'Balança', Icons.scale_outlined),
      const RailEntry(PdvDestination.settings, 'Mais', Icons.apps_outlined),
    ];
    return Container(
      width: 72,
      decoration: BoxDecoration(
        color: scheme.surface,
        border: Border(right: BorderSide(color: scheme.outlineVariant)),
      ),
      child: Column(
        children: [
          SizedBox(
            height: 58,
            child: Center(
              child: Image.asset('assets/logoicon.png', width: 34, height: 34),
            ),
          ),
          Divider(height: 1, color: scheme.outlineVariant),
          const SizedBox(height: 8),
          // ROLA QUANDO NÃO CABE. São oito destinos de 58 px: numa tela baixa
          // (ou com a janela reduzida) a coluna estourava e o último botão
          // ficava cortado — uma tela inalcançável de novo, agora por altura.
          Expanded(
            child: SingleChildScrollView(
              child: Column(
                children: [
                  for (final entry in entries)
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 7,
                        vertical: 3,
                      ),
                      child: RailButton(
                        entry: entry,
                        selected: _isSelected(entry.destination),
                        onTap: () => onSelected(entry.destination),
                      ),
                    ),
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.only(bottom: 10),
            child: Tooltip(
              message:
                  'Ajuda e atalhos: ${PdvShortcuts.teclaDe(PdvAction.help)}',
              child: Text(
                PdvShortcuts.teclaDe(PdvAction.help),
                style: TextStyle(
                  color: scheme.onSurfaceVariant,
                  fontSize: 12,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  bool _isSelected(PdvDestination destination) => selected == destination;
}
