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

  /// A aba Comandas: abre o cartão lido — livre ou ocupado — e SÓ ele.
  ///
  /// Antes caía na busca em memória, que abria "a única comanda que sobrou na
  /// lista filtrada" quando nada casava exato: com a busca guardando um texto
  /// antigo, o cartão 17 abriu a comanda 107.
  Future<void> _openCommandFromCode(String lido) =>
      mostrandoComandaLida(context, lido, () async {
        final ativas = commands.where((item) => item['is_active'] != false);
        var comanda = comandaLidaNaLista(ativas, lido);
        if (comanda == null) {
          // A lista pode não ter descido inteira: o servidor responde.
          final lookup = _codeLookup;
          if (lookup == null) return;
          comanda = (await lookup.findCommand(lido)).command;
        }
        if (!mounted || comanda == null) return;
        if (!_conferirComandaLida(lido, comanda)) return;
        await _openCommand(comanda);
      });

  /// A comanda achada é mesmo a do cartão lido? Senão, avisa e NÃO abre.
  ///
  /// A última trava antes de lançar na conta de alguém. As buscas já casam
  /// exato, mas uma rota nova que esqueça disso não pode abrir a 107 quando o
  /// cartão é o 17. A leitura crua vai para o log: é ela que diz, depois, se o
  /// leitor trocou dígitos ou se o casamento falhou.
  bool _conferirComandaLida(String lido, Map<String, dynamic> comanda) {
    final confere = comandaCasaComLido(comanda, lido);
    AppLogger.instance.info(
      'comanda_lida',
      data: {
        'lido': lido,
        'numero': '${comanda['number'] ?? ''}',
        'codigo': '${comanda['code'] ?? ''}',
        'confere': confere,
      },
    );
    if (confere) return true;
    _error(
      ApiException(
        'O leitor leu ${numeroLidoParaExibir(lido)}, mas a comanda encontrada '
        'é a ${comanda['number'] ?? '?'}. Nada foi aberto: passe o cartão de '
        'novo.',
      ),
    );
    return false;
  }

  /// O cartão lido vira o DESTINO do que está na tela.
  ///
  /// Com rascunho no ar, anexa — sem tocar no servidor e sem perder o que já
  /// foi passado. Com pedido aberto, abre o pedido daquele cartão, que é o que
  /// a leitura sempre fez nas outras telas: o operador está dizendo "agora é
  /// esta comanda".
  void _useCommandFromCode(Map<String, dynamic> comanda) {
    // Cartão LIVRE não entra: não há consumo a cobrar.
    //
    // A mesma regra que a conta agrupada já aplica no servidor
    // (`_assert_source_is_mergeable`), e de propósito com a mesma frase — a
    // recusa precisa ser a mesma nos dois lugares, senão o operador aprende
    // duas explicações para o mesmo "não".
    //
    // Sem isto, passar um cartão vazio por engano prendia um pedido novo a um
    // cartão que ninguém estava usando, e alguém tinha de cancelar depois.
    if (!comandaTemContaAberta(comanda)) {
      _error(
        ApiException(
          'A comanda ${comanda['number'] ?? ''} não tem um pedido aberto: '
          'não há nada a cobrar nela.',
        ),
      );
      return;
    }
    // A cópia da lista local traz os campos que a tela já carregou (a mesa
    // vinculada, entre eles); a do servidor é o retrato mais novo. Preferir a
    // local mantém o cartão idêntico ao que está desenhado ao lado.
    final local = commands.cast<Map<String, dynamic>?>().firstWhere(
      (item) => '${item?['id']}' == '${comanda['id']}',
      orElse: () => null,
    );
    final escolhida = local ?? comanda;

    if (_draftIsLive) {
      _attachCommandToDraftDirectly(escolhida);
      return;
    }
    // Pedido já aberto: o cartão lido é "agora é esta comanda", que é o que a
    // leitura sempre fez nas outras telas.
    unawaited(_openCommand(escolhida));
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
          await _openCommandFromCode(scanned.value);
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
      // Clientes não reage a código: o leitor do balcão lê comanda e produto,
      // e um código caindo aqui só encheria a busca com o que ela não acha.
      case PdvScreen.customers:
      case PdvScreen.payment:
      case PdvScreen.cash:
      case PdvScreen.settings:
      case PdvScreen.scale:
        break;
    }
  }
}
