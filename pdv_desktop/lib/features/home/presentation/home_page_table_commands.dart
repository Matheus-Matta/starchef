// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Quem está sentado NESTA mesa: sentar mais um cartão, tirar um cartão.
///
/// Mora fora de `_CommandSection` porque é a tela da MESA, e não a do cartão —
/// e porque o diálogo usado aqui é o mesmo da venda, não o formulário de
/// digitar número que existia antes.
mixin _TableCommandsSection on _CommandSection {
  /// As comandas sentadas na mesa aberta, como o painel as desenha.
  List<Map<String, dynamic>> get _commandsAtTable =>
      (selectedTable?['active_commands'] as List? ?? const [])
          .cast<Map<String, dynamic>>();

  /// Relê a mesa aberta a partir do catálogo recém-carregado.
  ///
  /// `_load()` troca a LISTA de mesas, não o mapa que `selectedTable` segura.
  /// Sem isto, sentar ou tirar um cartão recarregava tudo e a tela continuava
  /// mostrando as comandas de antes — o operador clicava de novo achando que
  /// o primeiro clique não pegou.
  void _refreshSelectedTable() {
    final id = '${selectedTable?['id'] ?? ''}';
    if (id.isEmpty) return;
    final atual = tables.cast<Map<String, dynamic>?>().firstWhere(
      (table) => '${table?['id']}' == id,
      orElse: () => null,
    );
    if (atual != null) setState(() => selectedTable = atual);
  }

  /// Senta mais um cartão na mesa — ou tira um dos que já estão nela.
  ///
  /// É o MESMO diálogo do "anexar comanda" da venda, e de propósito: são a
  /// mesma pergunta ("qual cartão?") feita em telas diferentes, e duas listas
  /// com aparências distintas fariam o operador aprender duas vezes.
  ///
  /// A diferença é que aqui entram os cartões LIVRES também. Na venda um
  /// cartão sem consumo não acrescenta nada à conta; na mesa, sentar um cartão
  /// zerado é exatamente o começo do atendimento.
  Future<void> _seatCommandAtTable() async {
    final table = selectedTable;
    if (table == null || busy) return;

    final resultado = await showCommandAttachDialog(
      context,
      commands: commands,
      attached: _commandsAtTable,
      title: 'Comandas da mesa ${table['number']}',
      somenteComConta: false,
    );
    if (resultado == null || !mounted) return;

    if (resultado.isDetach) {
      final saindo = _commandsAtTable.cast<Map<String, dynamic>?>().firstWhere(
        (item) => '${item?['id']}' == resultado.detachedId,
        orElse: () => null,
      );
      if (saindo != null) await _unlinkCommandFromTable(saindo);
      return;
    }

    final entrando = resultado.command;
    if (entrando == null) return;

    // O teto é do restaurante (`max_commands_per_table`). O servidor barra de
    // qualquer jeito (409); aqui só evita a viagem e explica antes.
    final limite = _commandsPerTableLimit;
    if (limite > 0 && _commandsAtTable.length >= limite) {
      showAppToast(
        context,
        'Mesa ${table['number']} já tem ${_commandsAtTable.length} comanda(s); '
        'o limite do restaurante é $limite por mesa. Use outra mesa ou ajuste '
        'em Restaurantes > Operação.',
        severity: AppErrorSeverity.failure,
      );
      return;
    }

    try {
      setState(() => busy = true);
      await api.post(
        '/commands/${entrando['id']}/link-table/',
        body: {'table_id': table['id']},
        accessToken: token,
      );
      if (!mounted) return;
      await _load();
      if (mounted) _refreshSelectedTable();
    } catch (error) {
      _error(error, title: 'Não foi possível vincular a comanda à mesa');
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  /// Tira o cartão da mesa. O consumo dele não é tocado — ele só deixa de
  /// estar sentado ali.
  Future<void> _unlinkCommandFromTable(Map<String, dynamic> command) async {
    if (busy) return;
    await _unlinkCommand(command);
    if (mounted) _refreshSelectedTable();
  }
}
