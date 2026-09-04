// Nesta biblioteca cada seção da tela é um mixin, e um membro definido aqui é
// consumido por outra seção através da declaração abstrata dela. O analisador
// não liga as duas pontas entre mixins e marca tudo como `unused_element`.
//
// O custo assumido: código realmente morto NESTE arquivo também deixa de ser
// apontado. É menos ruim do que dezenas de `ignore` espalhados escondendo
// exatamente a mesma coisa, um a um, sem explicar por quê.
// ignore_for_file: unused_element, unused_element_parameter

part of 'home_page.dart';

/// Os painéis de contexto: escolher a mesa, escolher a comanda.
///
/// Separados das ações (`_CommandSection`) — vincular, transferir, abrir.
mixin _CommandView on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  List<Map<String, dynamic>> get tables;
  List<Map<String, dynamic>> get commands;
  String get flowStep;
  set flowStep(String value);
  String? get orderType;
  set orderType(String? value);
  String get commandSearch;
  set commandSearch(String value);
  FocusNode get commandSearchFocus;
  bool get isSecondaryStation;
  bool get principalReachable;

  Future<void> _load();
  Future<void> _openTable(Map<String, dynamic> table);
  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _transferCommandDialog(Map<String, dynamic> command);
  Future<void> _transferAllCommandsDialog();
  Future<void> _unlinkCommand(Map<String, dynamic> command);

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
