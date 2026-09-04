// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Comandas e mesas: vincular, desvincular, transferir, abrir — e os dois
/// painéis de contexto que o operador vê antes de lançar o primeiro item.
///
/// Os métodos foram MOVIDOS, não reescritos.
mixin _CommandSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  set activeOrder(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedTable;
  set selectedTable(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCommand;
  set selectedCommand(Map<String, dynamic>? value);
  Map<String, dynamic>? get selectedCustomer;
  set selectedCustomer(Map<String, dynamic>? value);
  Map<String, dynamic>? get cashSession;
  String? get orderType;
  set orderType(String? value);
  List<Map<String, dynamic>> get orderItems;
  set orderItems(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get tables;
  set tables(List<Map<String, dynamic>> value);
  List<Map<String, dynamic>> get commands;
  set commands(List<Map<String, dynamic>> value);
  String get commandSearch;
  set commandSearch(String value);
  FocusNode get commandSearchFocus;
  String get flowStep;
  set flowStep(String value);
  bool get isSecondaryStation;
  bool get principalReachable;

  Future<void> _load();
  bool _isOfflinePending(Map<String, dynamic>? value);
  Future<void> _refreshOrder();
  Future<void> _openTable(Map<String, dynamic> table);
  Map<String, dynamic> _completeOfflineOrder(
    Map<String, dynamic> order, {
    required String type,
    Map<String, dynamic>? table,
    Map<String, dynamic>? command,
  });

  // Kept temporarily for compatibility with queued mutations from older PDV
  // builds; no current PDV surface calls these waiter-only actions.
  Future<void> _linkCommandDialog() async {
    final searchController = TextEditingController();
    final action = await showDialog<String>(
      context: context,
      builder: (dialogContext) => AppDialog(
        title: const Text('Vincular Comanda'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text('Digite ou bipe o número/código da comanda:'),
            const SizedBox(height: 16),
            TextField(
              controller: searchController,
              autofocus: true,
              decoration: const InputDecoration(
                prefixIcon: Icon(Icons.search_rounded),
                hintText: 'Número ou código...',
              ),
              onSubmitted: (value) => Navigator.pop(dialogContext, value),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () =>
                Navigator.pop(dialogContext, searchController.text),
            child: const Text('Vincular'),
          ),
        ],
      ),
    );

    if (action != null && action.trim().isNotEmpty && mounted) {
      final term = action.trim().toLowerCase();
      final command = commands.cast<Map<String, dynamic>?>().firstWhere(
        (c) =>
            '${c?['number']}' == term || '${c?['code']}'.toLowerCase() == term,
        orElse: () => null,
      );

      if (command == null) {
        showAppToast(
          context,
          'Comanda não encontrada.',
          severity: AppErrorSeverity.warning,
        );
        return;
      }

      if (selectedTable != null) {
        final capacity = selectedTable!['capacity'] ?? 0;
        final activeCommandsCount =
            (selectedTable!['active_commands'] as List? ?? []).length;
        if (capacity > 0 && activeCommandsCount >= capacity) {
          final confirm = await showDialog<bool>(
            context: context,
            builder: (ctx) => AppDialog(
              title: const Text('Lotação Atingida'),
              content: const Text(
                'A mesa já atingiu a sua capacidade máxima. Deseja vincular a comanda mesmo assim?',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx, false),
                  child: const Text('Cancelar'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(ctx, true),
                  child: const Text('Vincular'),
                ),
              ],
            ),
          );
          if (!mounted) return;
          if (confirm != true) return;
        }

        try {
          setState(() => busy = true);
          await api.post(
            '/commands/${command['id']}/link-table/',
            body: {'table_id': selectedTable!['id']},
            accessToken: token,
          );
          if (!mounted) return;
          await _load();
        } catch (e) {
          _error(e);
        } finally {
          if (mounted) setState(() => busy = false);
        }
      }
    }
  }

  Future<void> _unlinkCommand(Map<String, dynamic> command) async {
    try {
      setState(() => busy = true);
      await api.post(
        '/commands/${command['id']}/unlink-table/',
        body: const {},
        accessToken: token,
      );
      if (!mounted) return;
      await _load();
    } catch (e) {
      _error(e);
    } finally {
      if (mounted) setState(() => busy = false);
    }
  }

  Future<void> _transferCommandDialog(Map<String, dynamic> command) async {
    final tablesList = tables
        .where((t) => t['id'] != selectedTable?['id'])
        .toList();
    final destTable = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Transferir Comanda'),
        content: SizedBox(
          width: 400,
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: tablesList.length,
            separatorBuilder: (_, _) => const Divider(),
            itemBuilder: (_, index) {
              final t = tablesList[index];
              return ListTile(
                title: Text('Mesa ${t['number']}'),
                subtitle: Text(t['sector_name'] ?? ''),
                onTap: () => Navigator.pop(ctx, t),
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
        ],
      ),
    );

    if (destTable != null && mounted) {
      try {
        setState(() => busy = true);
        await api.post(
          '/commands/${command['id']}/link-table/',
          body: {'table_id': destTable['id']},
          accessToken: token,
        );
        if (!mounted) return;
        await _load();
      } catch (e) {
        _error(e);
      } finally {
        if (mounted) setState(() => busy = false);
      }
    }
  }

  Future<void> _transferAllCommandsDialog() async {
    final tablesList = tables
        .where((t) => t['id'] != selectedTable?['id'])
        .toList();
    final destTable = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (ctx) => AppDialog(
        title: const Text('Transferir Todas as Comandas'),
        content: SizedBox(
          width: 400,
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: tablesList.length,
            separatorBuilder: (_, _) => const Divider(),
            itemBuilder: (_, index) {
              final t = tablesList[index];
              return ListTile(
                title: Text('Mesa ${t['number']}'),
                subtitle: Text(t['sector_name'] ?? ''),
                onTap: () => Navigator.pop(ctx, t),
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar'),
          ),
        ],
      ),
    );

    if (destTable != null && mounted && selectedTable != null) {
      try {
        setState(() => busy = true);
        await api.post(
          '/tables/${selectedTable!['id']}/transfer-commands/',
          body: {'to_table_id': destTable['id']},
          accessToken: token,
        );
        if (!mounted) return;
        await _load();
      } catch (e) {
        _error(e);
      } finally {
        if (mounted) setState(() => busy = false);
      }
    }
  }

  /// Abre (ou retoma) o pedido de uma comanda.
  ///
  /// Espelha [_openTable]: comanda livre cria o pedido, comanda em uso retoma
  /// o que já existe. Quem decide é o servidor (`/orders/open-command/`), para
  /// que dois caixas lendo a mesma comanda não criem dois pedidos.
  Future<void> _openCommand(Map<String, dynamic> command) async {
    if (busy) return;
    final linkedTableId = command['current_table'];
    final table = linkedTableId == null
        ? null
        : tables.cast<Map<String, dynamic>?>().firstWhere(
            (item) => '${item?['id']}' == '$linkedTableId',
            orElse: () => null,
          );

    final tableForCommand = table;
    await _work(() async {
      selectedCommand = command;
      selectedTable = tableForCommand;
      final currentId = command['current_order_id'];
      final order = currentId != null
          ? await api.get('/orders/$currentId/', accessToken: token)
          : await api.post(
              '/orders/open-command/',
              body: {'command': command['id']},
              accessToken: token,
              // Mesa e comanda só existem na tela; o repositório precisa
              // delas para montar o pedido local completo.
              localContext: {'command': command, 'table': ?selectedTable},
            );
      activeOrder = _completeOfflineOrder(
        order,
        type: 'command',
        command: command,
        table: selectedTable,
      );
      if (_isOfflinePending(activeOrder)) {
        command['status'] = 'occupied';
        command['current_order_id'] = activeOrder!['id'];
      }
      await _refreshOrder();
      flowStep = 'order';
    });
    // Fora do `_work` acima de propósito: ele marca `busy`, e o vínculo da
    // mesa faz a própria chamada de API.
    await _ensureCommandTable();
  }

  /// Pergunta em que mesa a comanda está sentada, quando ela ainda não tem
  /// vínculo.
  ///
  /// Vale tanto ao abrir um pedido novo quanto ao retomar um existente: sem
  /// isso uma comanda avulsa seguia o atendimento inteiro sem mesa, e o salão
  /// não tinha como saber onde entregar. Continua sendo possível seguir sem
  /// mesa — self-service é um caso legítimo —, mas agora é uma escolha
  /// explícita do operador, não um silêncio.
  Future<void> _ensureCommandTable() async {
    final command = selectedCommand;
    if (!mounted ||
        command == null ||
        selectedTable != null ||
        command['current_table'] != null) {
      return;
    }
    final available = tables
        .where((table) => '${table['status']}' != 'inactive')
        .toList(growable: false);
    if (available.isEmpty) return;

    final chosen = await showDialog<Map<String, dynamic>>(
      context: context,
      builder: (dialogContext) => AppDialog(
        title: Text('Comanda ${command['code'] ?? command['number'] ?? ''}'),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text('Em qual mesa esta comanda está?'),
              const SizedBox(height: 12),
              Flexible(
                child: ListView.separated(
                  shrinkWrap: true,
                  itemCount: available.length,
                  separatorBuilder: (_, _) => const Divider(height: 1),
                  itemBuilder: (_, index) {
                    final table = available[index];
                    final occupied =
                        (table['active_commands'] as List? ?? const []).length;
                    final capacity = _number(table['capacity']).round();
                    return ListTile(
                      contentPadding: EdgeInsets.zero,
                      leading: const Icon(Icons.table_restaurant_outlined),
                      title: Text('Mesa ${table['number']}'),
                      subtitle: Text(
                        [
                          '${table['sector_name'] ?? ''}'.trim(),
                          if (capacity > 0) '$occupied/$capacity comandas',
                        ].where((part) => part.isNotEmpty).join(' · '),
                      ),
                      onTap: () => Navigator.pop(dialogContext, table),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext),
            child: const Text('Seguir sem mesa'),
          ),
        ],
      ),
    );
    if (chosen == null || !mounted) return;

    try {
      await api.post(
        '/commands/${command['id']}/link-table/',
        body: {'table_id': chosen['id']},
        accessToken: token,
      );
      if (!mounted) return;
      setState(() {
        selectedTable = chosen;
        command['current_table'] = chosen['id'];
        activeOrder = {
          ...?activeOrder,
          'table': chosen['id'],
          'table_number': chosen['number'],
        };
      });
    } catch (error) {
      if (mounted) {
        _error(
          error,
          title: 'Não foi possível vincular a comanda à mesa',
          action: 'O pedido segue aberto; tente vincular de novo pela mesa.',
        );
      }
    }
  }
}
