import '../../../core/input/pdv_shortcuts.dart';
import 'pdv_navigation_shell.dart';

/// A página de cada tecla de função: F1 a F8, na ordem do menu lateral.
///
/// Fica fora do catálogo (`pdv_shortcuts.dart`) porque o catálogo é do núcleo
/// e não conhece as páginas desta tela.
const paginaDoAtalho = <String, PdvDestination>{
  PdvAction.goSale: PdvDestination.sale,
  PdvAction.goOrders: PdvDestination.orders,
  PdvAction.goTables: PdvDestination.tables,
  PdvAction.goCommands: PdvDestination.commands,
  PdvAction.goCustomers: PdvDestination.customers,
  PdvAction.goCash: PdvDestination.finance,
  PdvAction.goScale: PdvDestination.scale,
  PdvAction.goSettings: PdvDestination.settings,
};

/// A tecla que abre [pagina] ("F3"), para o menu lateral mostrar.
String teclaDaPagina(PdvDestination pagina) {
  for (final entrada in paginaDoAtalho.entries) {
    if (entrada.value == pagina) return PdvShortcuts.teclaDe(entrada.key);
  }
  return '';
}
