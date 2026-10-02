import 'package:flutter/material.dart';

import '../data/command_pager.dart';

/// Grade de comandas que pede a próxima página quando a rolagem chega perto
/// do fim.
///
/// Serve às DUAS telas — o salão de comandas e o "Selecione a comanda" da
/// venda —, que só diferem no desenho do cartão ([itemBuilder]).
class CommandsPagedGrid extends StatefulWidget {
  const CommandsPagedGrid({
    super.key,
    required this.paginador,
    required this.itemBuilder,
    required this.vazio,
  });

  final CommandPager paginador;
  final Widget Function(BuildContext context, Map<String, dynamic> comanda)
  itemBuilder;

  /// O que aparece quando a busca (ou a loja) não tem comanda nenhuma.
  ///
  /// É uma função, e não um widget pronto, porque o texto depende da busca
  /// ATUAL: montado antes, ele dizia "nenhuma cadastrada" depois de uma busca
  /// que só não achou nada.
  final WidgetBuilder vazio;

  /// A que distância do fim a próxima página já é pedida. Chegar ao fim e
  /// ESPERAR a página é o que faz a rolagem engasgar.
  static const margemDoFim = 400.0;

  @override
  State<CommandsPagedGrid> createState() => _CommandsPagedGridState();
}

class _CommandsPagedGridState extends State<CommandsPagedGrid> {
  final _rolagem = ScrollController();

  @override
  void initState() {
    super.initState();
    _rolagem.addListener(_talvezMais);
    widget.paginador.addListener(_depoisDaPagina);
    // A primeira página pode ter chegado antes da grade existir — e aí
    // nenhum aviso do paginador viria conferir se ela encheu a tela.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _talvezMais();
    });
  }

  @override
  void didUpdateWidget(CommandsPagedGrid antigo) {
    super.didUpdateWidget(antigo);
    if (antigo.paginador != widget.paginador) {
      antigo.paginador.removeListener(_depoisDaPagina);
      widget.paginador.addListener(_depoisDaPagina);
    }
  }

  @override
  void dispose() {
    widget.paginador.removeListener(_depoisDaPagina);
    _rolagem.dispose();
    super.dispose();
  }

  void _talvezMais() {
    if (!_rolagem.hasClients) return;
    if (_rolagem.position.extentAfter < CommandsPagedGrid.margemDoFim) {
      widget.paginador.carregarMais();
    }
  }

  /// Numa tela alta, 50 cartões podem não encher a grade — e sem barra de
  /// rolagem não há rolagem que peça a página seguinte. Confere depois de
  /// desenhar e pede mais até encher (ou acabar).
  void _depoisDaPagina() {
    if (!mounted) return;
    setState(() {});
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _talvezMais();
    });
  }

  @override
  Widget build(BuildContext context) {
    final paginador = widget.paginador;
    final itens = paginador.itens;
    if (itens.isEmpty && !paginador.carregando && paginador.erro.isEmpty) {
      return widget.vazio(context);
    }
    return CustomScrollView(
      controller: _rolagem,
      slivers: [
        SliverGrid.builder(
          gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
            maxCrossAxisExtent: 170,
            childAspectRatio: 1.05,
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
          ),
          itemCount: itens.length,
          itemBuilder: (context, indice) =>
              widget.itemBuilder(context, itens[indice]),
        ),
        SliverToBoxAdapter(child: _rodape(context, paginador)),
      ],
    );
  }

  Widget _rodape(BuildContext context, CommandPager paginador) {
    final scheme = Theme.of(context).colorScheme;
    if (paginador.erro.isNotEmpty) {
      return Padding(
        padding: const EdgeInsets.symmetric(vertical: 16),
        child: Column(
          children: [
            Text(paginador.erro, style: TextStyle(color: scheme.error)),
            const SizedBox(height: 8),
            OutlinedButton.icon(
              onPressed: paginador.tentarDeNovo,
              icon: const Icon(Icons.refresh_rounded),
              label: const Text('Tentar de novo'),
            ),
          ],
        ),
      );
    }
    if (paginador.carregando) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 16),
        child: Center(
          child: SizedBox.square(
            dimension: 24,
            child: CircularProgressIndicator(strokeWidth: 2.5),
          ),
        ),
      );
    }
    final total = paginador.total;
    if (paginador.temMais || total == null) return const SizedBox(height: 16);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 16),
      child: Center(
        child: Text(
          total == 1 ? '1 comanda' : '$total comandas',
          style: TextStyle(color: scheme.onSurfaceVariant),
        ),
      ),
    );
  }
}
