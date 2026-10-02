import 'package:flutter/material.dart';

import '../../../core/widgets/shadcn_layout.dart';
import '../data/command_pager.dart';
import '../data/command_repository.dart';
import 'command_picker_tile.dart';
import 'commands_paged_grid.dart';

/// O "Selecione a comanda" da venda: busca no servidor e grade com rolagem.
///
/// Digitar um número já busca aquela comanda — no servidor, porque a grade só
/// tem as páginas que desceram, e a 480 de uma loja com 500 ainda não veio.
/// Enter abre a de número (ou código) EXATO; o leitor de cartão é um teclado
/// que digita o código e manda Enter.
class CommandPicker extends StatefulWidget {
  const CommandPicker({
    super.key,
    required this.repository,
    required this.onOpen,
    this.restaurantId,
    this.catalogo = const [],
    this.buscaInicial = '',
    this.onBuscaMudou,
    this.focusNode,
  });

  final CommandRepository repository;
  final String? restaurantId;
  final ValueChanged<Map<String, dynamic>> onOpen;

  /// As comandas do catálogo do PDV, que o tempo real mantém em dia.
  ///
  /// A página que desceu é uma foto do momento da busca; o catálogo sabe que
  /// a comanda 12 foi ocupada no outro caixa um segundo depois. A grade
  /// mostra a versão do catálogo quando ela existe.
  final List<Map<String, dynamic>> catalogo;
  final String buscaInicial;
  final ValueChanged<String>? onBuscaMudou;
  final FocusNode? focusNode;

  @override
  State<CommandPicker> createState() => _CommandPickerState();
}

class _CommandPickerState extends State<CommandPicker> {
  late final _busca = TextEditingController(text: widget.buscaInicial);
  late final _paginador = CommandPager(
    ({required int pagina, String busca = ''}) => widget.repository.page(
      pagina: pagina,
      busca: busca,
      restaurantId: widget.restaurantId,
    ),
  );

  @override
  void initState() {
    super.initState();
    _paginador.recomecar(busca: widget.buscaInicial);
  }

  @override
  void dispose() {
    _paginador.dispose();
    _busca.dispose();
    super.dispose();
  }

  /// Número ou código exato abre direto; um resultado só, também.
  ///
  /// Busca de novo antes, sem a espera da digitação: o leitor manda Enter
  /// logo depois do último caractere, antes da busca atrasada ter saído.
  Future<void> _confirmar(String valor) async {
    final termo = valor.trim();
    if (termo.isEmpty) return;
    await _paginador.buscarJa(termo);
    if (!mounted || _paginador.busca != termo) return;
    final achadas = _paginador.itens;
    final exata = achadas
        .where(
          (c) => '${c['number']}' == termo || '${c['code'] ?? ''}' == termo,
        )
        .firstOrNull;
    final comanda =
        exata ??
        (achadas.length == 1 && !_paginador.temMais ? achadas.first : null);
    if (comanda != null) widget.onOpen(_atual(comanda));
  }

  Map<String, dynamic> _atual(Map<String, dynamic> comanda) =>
      widget.catalogo.where((c) => c['id'] == comanda['id']).firstOrNull ??
      comanda;

  @override
  Widget build(BuildContext context) {
    final porId = {for (final c in widget.catalogo) c['id']: c};
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          controller: _busca,
          autofocus: true,
          focusNode: widget.focusNode,
          onChanged: (valor) {
            widget.onBuscaMudou?.call(valor);
            _paginador.digitar(valor);
          },
          onSubmitted: _confirmar,
          decoration: const InputDecoration(
            prefixIcon: Icon(Icons.search_rounded),
            hintText: 'Buscar por número, código ou cliente...',
          ),
        ),
        const SizedBox(height: 18),
        Expanded(
          child: CommandsPagedGrid(
            paginador: _paginador,
            vazio: (_) => AppEmptyState(
              icon: Icons.qr_code_2_outlined,
              title: _paginador.busca.isEmpty
                  ? 'Nenhuma comanda cadastrada'
                  : 'Nenhuma comanda encontrada',
              description: _paginador.busca.isEmpty
                  ? 'Cadastre comandas na retaguarda para iniciar atendimentos.'
                  : 'Tente buscar por outro número, código ou cliente.',
            ),
            itemBuilder: (_, comanda) {
              final atual = porId[comanda['id']] ?? comanda;
              return CommandPickerTile(
                comanda: atual,
                onTap: () => widget.onOpen(atual),
              );
            },
          ),
        ),
      ],
    );
  }
}
