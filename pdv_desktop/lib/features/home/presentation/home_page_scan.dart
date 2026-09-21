// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// O que um código LIDO faz — e o que ele faz depende da tela.
///
/// Separado dos atalhos de teclado porque são duas entradas com regras
/// diferentes: a tecla é sempre do operador, e o código pode vir do leitor sem
/// ninguém olhar para a tela. É por isso que cada tela decide o que aceitar, e
/// pagamento, caixa e configurações não aceitam nada.
mixin _ScanSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  String? get orderType;
  String get flowStep;
  String get orderSearch;
  set orderSearch(String value);
  String? get scanningProductId;
  StreamController<void>? get productScanRepeats;
  List<Map<String, dynamic>> get commands;
  CodeLookupService? get codeLookup;
  set codeLookup(CodeLookupService? value);
  TextEditingController get ordersSearchController;
  PdvScreen get _currentScreen;
  StreamController<String> get commandPageCodes;

  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _configureProduct(Map<String, dynamic> product);
  void _onCommandSearchSubmitted(String value);

  // ── as ações, em `home_page_scan_actions.dart` ──────────────────────────
  Future<void> _openOrderFromCommandCode(
    String code, {
    VoidCallback? onNotFound,
  });
  Future<void> _onSaleScreenCode(String code);

  @override
  CodeLookupService? get _codeLookup {
    if (token.isEmpty) return null;
    return codeLookup ??= CodeLookupService(api, accessToken: token);
  }

  /// Um código chegou — de onde quer que tenha vindo.
  Future<void> _onCodeScanned(ScannedCode scanned) async {
    switch (_currentScreen) {
      case PdvScreen.home:
        await _openOrderFromCommandCode(scanned.value);
      case PdvScreen.context:
        // A busca em memória (por número/código exato da lista já filtrada)
        // continua servindo a aba Comandas, que tem seu próprio campo de
        // busca e convive bem com múltiplos resultados. A aba Mesas não tem
        // campo de busca nenhum, então usa a mesma consulta ao banco local
        // que a tela inicial usa — robusta mesmo com `commands` desatualizado.
        if (orderType == 'command') {
          _onCommandSearchSubmitted(scanned.value);
        } else {
          await _openOrderFromCommandCode(scanned.value);
        }
      case PdvScreen.order:
        await _onSaleScreenCode(scanned.value);
      case PdvScreen.orders:
        // Bipar uma comanda abre direto o pedido em aberto dela; qualquer
        // outro código (produto, número de pedido) só preenche a busca da
        // lista, como antes.
        await _openOrderFromCommandCode(
          scanned.value,
          onNotFound: () {
            ordersSearchController.text = scanned.value;
            setState(() => orderSearch = scanned.value);
          },
        );
      case PdvScreen.commands:
        // A página das comandas resolve o código por conta própria: ali o
        // cartão lido ABRE A COMANDA na tela, e não o pedido dela. Sair para o
        // pedido seria o contrário do que se foi fazer lá — conferir.
        commandPageCodes.add(scanned.value);
      case PdvScreen.payment:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }
}
