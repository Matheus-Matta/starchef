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

  Future<void> _load();
  Future<void> _openTable(Map<String, dynamic> table);
  Future<void> _openCommand(Map<String, dynamic> command);
  Future<void> _openCommandFromCode(String lido);
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
                flowStep = 'order';
                orderType = 'counter';
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
                  final occupied = tableIsOccupied(table);
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
                                tableStatusLabel(table),
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

  /// Comandas ativas do catálogo, filtradas por número, código ou cliente.
  ///
  /// A GRADE da tela busca no servidor, página a página ([CommandPicker]).
  /// Isto aqui atende o que chega sem passar pelo campo — o Enter global e o
  /// leitor de cartão —, e o catálogo do PDV já tem todas as comandas.
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

  /// Enter no campo de busca — digitado, ou o leitor com o campo focado.
  ///
  /// NÚMERO só abre por casamento exato (`0017` é a 17, e só ela). Antes,
  /// sem casamento exato, abria "a única comanda que sobrou na lista
  /// filtrada": com um texto antigo na busca, o cartão 17 abriu a 107. A
  /// sobra única continua valendo para NOME, que é como uma pessoa procura.
  void _onCommandSearchSubmitted(String value) {
    final term = value.trim();
    if (term.isEmpty) return;
    if (RegExp(r'^\d+$').hasMatch(term)) {
      unawaited(_openCommandFromCode(term));
      return;
    }
    final exact = comandaLidaNaLista(visibleCommands, term);
    final matches = visibleCommands;
    final command = exact ?? (matches.length == 1 ? matches.first : null);
    if (command != null) _openCommand(command);
  }

  Widget _commandContextPanel() {
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
                  flowStep = 'order';
                  orderType = 'counter';
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
              Expanded(
                child: CommandPicker(
                  repository: CommandRepository(api, accessToken: token),
                  restaurantId: restaurantId,
                  catalogo: commands,
                  buscaInicial: commandSearch,
                  focusNode: commandSearchFocus,
                  // Sem setState: o texto só serve ao Enter global (ver
                  // [visibleCommands]); redesenhar a venda a cada letra não.
                  onBuscaMudou: (value) => commandSearch = value,
                  onOpen: _openCommand,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
