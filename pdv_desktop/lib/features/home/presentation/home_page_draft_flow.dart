// Ver a nota em `home_page_panels.dart`: nesta biblioteca cada seção é um
// mixin, e o analisador não liga as duas pontas entre eles.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Para onde o rascunho vai, e a hora em que ele vira pedido.
///
/// Separado de `_DraftSection`, que cuida do que ENTRA no carrinho. São dois
/// assuntos com ritmos diferentes: as linhas mudam a cada toque no catálogo, e
/// o destino é escolhido uma vez por atendimento.
mixin _DraftFlowSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCommand;
  set selectedCommand(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  set selectedTable(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCustomer;
  set selectedCustomer(Map<String, dynamic>? value);
  String? get orderType;
  set orderType(String? value);
  List<Map<String, dynamic>> get commands;
  List<Map<String, dynamic>> get tables;

  Future<void> _refreshOrder();
  Future<Map<String, dynamic>?> _chooseCustomer(String type);
  Future<void> _carregarItensDaComanda(Map<String, dynamic> command);

  // ── destino do rascunho ─────────────────────────────────────────────────

  @override
  Future<void> _pickDraftType(String type) async {
    if (type == 'command') {
      setState(() {
        draft.orderType = 'command';
        orderType = 'command';
      });
      // Sem comanda anexada ainda, o gesto seguinte é óbvio — abre o seletor
      // em vez de deixar o operador procurar o botão que acabou de aparecer.
      if (draft.command == null) await _attachCommandToDraft();
      return;
    }

    // Retirada e delivery são pedidos de BALCÃO: mudam o tipo do pedido — o
    // que importa para relatório e para a disponibilidade do produto — e nada
    // mais. Antes a aba abria um seletor de clientes e só seguia com um
    // escolhido, então em loja sem cliente cadastrado (ou com o operador
    // desistindo do diálogo) o toque simplesmente não fazia nada.
    //
    // O cliente continua podendo ser vinculado no pedido depois de aberto;
    // ele nunca foi obrigatório para cobrar.
    setState(() {
      draft.detachCommand();
      draft.orderType = type;
      draft.customer = null;
      orderType = type;
      selectedCommand = null;
      selectedTable = null;
      selectedCustomer = null;
    });
  }

  @override
  Future<void> _attachCommandToDraft() async {
    final command = await showCommandAttachDialog(context, commands: commands);
    if (command == null || !mounted) return;
    _attachCommandToDraftDirectly(command);
  }

  /// Anexa ESTE cartão, sem perguntar.
  ///
  /// Separado do diálogo porque há duas portas para o mesmo gesto: escolher na
  /// lista e passar o cartão no leitor. Duplicar o vínculo com a mesa nas duas
  /// faria uma delas esquecer a mesa quando o código mudasse — e a comanda
  /// seguiria o atendimento sem lugar no salão.
  @override
  void _attachCommandToDraftDirectly(Map<String, dynamic> command) {
    // A mesa vem da COMANDA: é ela que decide a ocupação do salão, e o pedido
    // guarda a mesa só como histórico.
    final linkedTableId = command['current_table'];
    final table = linkedTableId == null
        ? null
        : tables.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '$linkedTableId',
            orElse: () => null,
          );
    setState(() {
      draft.attachCommand(command, at: table);
      orderType = 'command';
      selectedCommand = command;
      selectedTable = table;
    });
    unawaited(_carregarItensDaComanda(command));
  }

  /// Solta UM cartão da conta. Sem id, solta todos.
  @override
  void _detachCommandFromDraft([String? commandId]) {
    setState(() {
      draft.detachCommand(commandId);
      // O tipo e a seleção acompanham o que SOBROU: soltar um de quatro não
      // devolve o pedido ao balcão.
      orderType = draft.orderType;
      selectedCommand = draft.command;
      selectedTable = draft.table;
    });
  }

  // ── materialização ──────────────────────────────────────────────────────

  /// Abre o pedido no servidor com tudo o que está no rascunho.
  ///
  /// Devolve `true` quando a tela passou a ter um `activeOrder` — seja porque
  /// ele acabou de nascer, seja porque já existia. `false` quando a operação
  /// falhou: o rascunho continua intacto, e quem chamou deve PARAR em vez de
  /// seguir para a cozinha ou para o pagamento.
  @override
  Future<bool> _materializeDraft() async {
    if (activeOrder != null) return true;
    if (draft.isEmpty) return false;

    final pedido = await _work(() async {
      final materializer = OrderDraftMaterializer(api, accessToken: token);
      return await materializer.materialize(draft, restaurantId: restaurantId);
    }, errorTitle: 'Não foi possível abrir o pedido');

    if (pedido == null || !mounted) return false;

    activeOrder = pedido;
    selectedCommand = draft.command;
    selectedTable = draft.table;
    selectedCustomer = draft.customer;
    orderType = draft.orderType;
    // Só AGORA o rascunho pode morrer: o pedido existe e os itens estão
    // dentro dele. Limpar antes custaria o carrinho inteiro se a criação
    // falhasse no meio, com o cliente na frente.
    draft.clear();
    await _refreshOrder();
    if (mounted) setState(() {});
    return true;
  }

  /// Joga fora o rascunho ao sair da tela.
  ///
  /// É o irmão de `_leaveActiveOrder` para o que ainda não nasceu: não há o
  /// que cancelar no servidor, porque nada foi criado lá. Esta é justamente a
  /// vantagem de adiar — abandonar sai de graça.
  @override
  void _discardDraft() {
    if (draft.isEmpty && draft.command == null) return;
    draft.clear();
  }
}
