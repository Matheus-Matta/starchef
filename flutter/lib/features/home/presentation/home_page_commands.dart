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
  // ignore: unused_element
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

  // ignore: unused_element
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

  // ignore: unused_element
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

  // ignore: unused_element
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

  Widget _tableContextPanel() => Center(
    child: ConstrainedBox(
      constraints: const BoxConstraints(maxWidth: 1400),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            TextButton.icon(
              onPressed: () => setState(() {
                flowStep = 'type';
                orderType = null;
              }),
              icon: const Icon(Icons.arrow_back),
              label: const Text('Voltar'),
            ),
            const SizedBox(height: 10),
            Text(
              'Selecione a mesa',
              style: Theme.of(
                context,
              ).textTheme.headlineMedium?.copyWith(fontWeight: FontWeight.w900),
            ),
            const SizedBox(height: 5),
            Text(
              'A mesa fica ocupada enquanto houver uma comanda vinculada.',
              style: TextStyle(
                color: Theme.of(context).colorScheme.onSurfaceVariant,
              ),
            ),
            const SizedBox(height: 22),
            Expanded(
              child: GridView.builder(
                gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
                  maxCrossAxisExtent: 170,
                  childAspectRatio: 1.05,
                  crossAxisSpacing: 12,
                  mainAxisSpacing: 12,
                ),
                itemCount: tables.length,
                itemBuilder: (_, index) {
                  final table = tables[index];
                  final occupied =
                      table['status'] == 'occupied' ||
                      (table['active_commands'] as List? ?? const [])
                          .isNotEmpty;
                  final color = occupied ? Colors.orange : Colors.green;
                  return ShadCard(
                    padding: EdgeInsets.zero,
                    radius: AppTheme.radius,
                    shadows: const [],
                    border: ShadBorder.all(color: color.shade300),
                    columnCrossAxisAlignment: CrossAxisAlignment.stretch,
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        borderRadius: AppTheme.radius,
                        onTap: () => _openTable(table),
                        child: Padding(
                          padding: const EdgeInsets.all(12),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Text(
                                    '${table['number']}',
                                    style: const TextStyle(
                                      fontSize: 24,
                                      fontWeight: FontWeight.w900,
                                    ),
                                  ),
                                  const Spacer(),
                                  Container(
                                    width: 9,
                                    height: 9,
                                    decoration: BoxDecoration(
                                      color: color,
                                      shape: BoxShape.circle,
                                    ),
                                  ),
                                ],
                              ),
                              const Spacer(),
                              Text(
                                occupied ? 'Ocupada' : 'Livre',
                                style: TextStyle(
                                  fontWeight: FontWeight.w700,
                                  color: color.shade800,
                                ),
                              ),
                              Text(
                                '${table['capacity'] ?? 0} lugares · ${table['sector_name'] ?? 'Sem setor'}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: 11,
                                  color: Theme.of(
                                    context,
                                  ).colorScheme.onSurfaceVariant,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    ),
  );

  /// Comandas ativas, filtradas por número, código escaneável ou cliente.
  ///
  /// A busca é local porque a lista inteira já veio no carregamento do PDV —
  /// e precisa continuar respondendo sem rede, que é quando o operador mais
  /// depende de achar a comanda pelo número impresso no cartão.
  List<Map<String, dynamic>> get visibleCommands {
    final term = commandSearch.trim().toLowerCase();
    final active = commands.where((item) => item['is_active'] != false);
    if (term.isEmpty) return active.toList();
    return active.where((item) {
      final haystack =
          '${item['number']} ${item['code'] ?? ''} '
                  '${item['customer_name'] ?? ''}'
              .toLowerCase();
      return haystack.contains(term);
    }).toList();
  }

  /// Abre a comanda direto quando o leitor bipa o código e envia Enter.
  ///
  /// Prioriza um match exato de número/código: com a lista já filtrada por
  /// [visibleCommands], vários cartões podem compartilhar prefixo (comanda 1
  /// e 10, por exemplo) e o texto digitado por um humano nunca dispara Enter.
  void _onCommandSearchSubmitted(String value) {
    final term = value.trim();
    if (term.isEmpty) return;
    final matches = visibleCommands;
    final exact = matches.cast<Map<String, dynamic>?>().firstWhere(
      (item) =>
          '${item?['number']}' == term || '${item?['code'] ?? ''}' == term,
      orElse: () => null,
    );
    final command = exact ?? (matches.length == 1 ? matches.first : null);
    if (command != null) _openCommand(command);
  }

  Widget _commandContextPanel() {
    final visible = visibleCommands;
    final free = commands
        .where((item) => item['is_active'] != false && item['status'] == 'free')
        .length;
    return Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 1400),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextButton.icon(
                onPressed: () => setState(() {
                  flowStep = 'type';
                  orderType = null;
                }),
                icon: const Icon(Icons.arrow_back),
                label: const Text('Voltar'),
              ),
              const SizedBox(height: 10),
              Text(
                'Selecione a comanda',
                style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                  fontWeight: FontWeight.w900,
                ),
              ),
              const SizedBox(height: 5),
              Text(
                '$free ${free == 1 ? 'comanda livre' : 'comandas livres'} · '
                'toque numa em uso para retomar o pedido.',
                style: TextStyle(
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                autofocus: true,
                focusNode: commandSearchFocus,
                onChanged: (value) => setState(() => commandSearch = value),
                onSubmitted: _onCommandSearchSubmitted,
                decoration: const InputDecoration(
                  prefixIcon: Icon(Icons.search_rounded),
                  hintText: 'Buscar por número, código ou cliente...',
                ),
              ),
              const SizedBox(height: 18),
              Expanded(
                child: visible.isEmpty
                    ? AppEmptyState(
                        icon: Icons.qr_code_2_outlined,
                        title: commands.isEmpty
                            ? 'Nenhuma comanda cadastrada'
                            : 'Nenhuma comanda encontrada',
                        description: commands.isEmpty
                            ? 'Cadastre comandas na retaguarda para iniciar atendimentos.'
                            : 'Tente buscar por outro número, código ou cliente.',
                      )
                    : GridView.builder(
                        gridDelegate:
                            const SliverGridDelegateWithMaxCrossAxisExtent(
                              maxCrossAxisExtent: 170,
                              childAspectRatio: 1.05,
                              crossAxisSpacing: 12,
                              mainAxisSpacing: 12,
                            ),
                        itemCount: visible.length,
                        itemBuilder: (_, index) {
                          final command = visible[index];
                          final occupied =
                              command['current_order_id'] != null ||
                              command['status'] == 'occupied';
                          final color = occupied ? Colors.orange : Colors.green;
                          return ShadCard(
                            padding: EdgeInsets.zero,
                            radius: AppTheme.radius,
                            shadows: const [],
                            border: ShadBorder.all(color: color.shade300),
                            columnCrossAxisAlignment:
                                CrossAxisAlignment.stretch,
                            child: InkWell(
                              onTap: () => _openCommand(command),
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Text(
                                          '${command['number']}',
                                          style: const TextStyle(
                                            fontSize: 24,
                                            fontWeight: FontWeight.w900,
                                          ),
                                        ),
                                        const Spacer(),
                                        Container(
                                          width: 9,
                                          height: 9,
                                          decoration: BoxDecoration(
                                            color: color,
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const Spacer(),
                                    Text(
                                      occupied ? 'Em uso' : 'Livre',
                                      style: TextStyle(
                                        fontWeight: FontWeight.w700,
                                        color: color.shade800,
                                      ),
                                    ),
                                    Text(
                                      '${command['customer_name']?.toString().trim().isNotEmpty == true ? command['customer_name'] : command['code'] ?? '—'}',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: TextStyle(
                                        fontSize: 11,
                                        color: Theme.of(
                                          context,
                                        ).colorScheme.onSurfaceVariant,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          );
                        },
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
