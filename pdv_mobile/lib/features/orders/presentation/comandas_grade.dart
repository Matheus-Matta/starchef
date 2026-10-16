import 'dart:async';

import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart';

import '../../../core/sync/backend_gateway.dart';
import '../../../core/widgets/shadcn_layout.dart';
import 'comanda_card.dart';
import 'comandas_presenter.dart';

/// A tela inicial: a busca pelo número FIXA no topo e a grade das comandas,
/// que carrega a próxima página conforme o garçom rola.
///
/// A busca fica fora da rolagem de propósito: com 200 cartões, o garçom que
/// rolou até o meio não precisa voltar ao topo para procurar o número.
class ComandasGrade extends StatefulWidget {
  const ComandasGrade({
    super.key,
    required this.presenter,
    required this.gateway,
    required this.onOpen,
  });

  final ComandasPresenter presenter;
  final BackendGateway gateway;
  final ValueChanged<Map<String, dynamic>> onOpen;

  @override
  State<ComandasGrade> createState() => _ComandasGradeState();
}

class _ComandasGradeState extends State<ComandasGrade> {
  final _scroll = ScrollController();
  final _busca = TextEditingController();
  Timer? _espera;

  ComandasPresenter get _p => widget.presenter;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_aoRolar);
  }

  @override
  void dispose() {
    _espera?.cancel();
    _scroll.dispose();
    _busca.dispose();
    super.dispose();
  }

  /// Pede a próxima página antes de bater no fim: ela chega enquanto o dedo
  /// ainda rola, e a grade não "pula".
  void _aoRolar() {
    if (!_scroll.hasClients) return;
    final falta = _scroll.position.maxScrollExtent - _scroll.position.pixels;
    if (falta < 500) _p.loadMore();
  }

  /// Espera o garçom parar de digitar: uma consulta por tecla afogaria a rede
  /// do salão à toa.
  void _aoDigitar(String texto) {
    setState(() {});
    _espera?.cancel();
    _espera = Timer(const Duration(milliseconds: 300), () => _p.buscar(texto));
  }

  void _limpar() {
    _busca.clear();
    _aoDigitar('');
  }

  @override
  Widget build(BuildContext context) => Column(
    children: [
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
        child: TextField(
          controller: _busca,
          keyboardType: TextInputType.number,
          textInputAction: TextInputAction.search,
          onChanged: _aoDigitar,
          onSubmitted: _p.buscar,
          decoration: InputDecoration(
            hintText: 'Número da comanda',
            prefixIcon: const Icon(Icons.search),
            suffixIcon: _busca.text.isEmpty
                ? null
                : IconButton(icon: const Icon(Icons.close), onPressed: _limpar),
          ),
        ),
      ),
      Expanded(
        child: RefreshIndicator(onRefresh: _p.load, child: _conteudo()),
      ),
    ],
  );

  Widget _conteudo() {
    final rows = _p.rows;
    if (rows.isEmpty && _p.loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (rows.isEmpty) {
      final erro = _p.error;
      return AppEmptyState(
        scrollable: true,
        icon: erro == null ? Icons.search_off : Icons.wifi_off,
        title: erro == null ? 'Nenhuma comanda' : 'Não foi possível carregar',
        description:
            erro ??
            (_p.search.isEmpty
                ? 'Nenhuma comanda cadastrada neste restaurante.'
                : 'Nenhuma comanda com "${_p.search}".'),
        action: erro == null
            ? null
            : ShadButton.outline(
                onPressed: _p.load,
                child: const Text('Tentar de novo'),
              ),
      );
    }
    final rodape = _p.hasMore || _p.error != null;
    // Em tela grande a primeira página cabe inteira e não há rolagem para
    // pedir a próxima: confere depois de desenhar.
    if (_p.hasMore) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _aoRolar());
    }
    return CustomScrollView(
      controller: _scroll,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: [
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
          sliver: SliverGrid.builder(
            gridDelegate: const SliverGridDelegateWithMaxCrossAxisExtent(
              maxCrossAxisExtent: 220,
              // Cabe o resumo do que a comanda tem (duas linhas).
              mainAxisExtent: 150,
              crossAxisSpacing: 10,
              mainAxisSpacing: 10,
            ),
            itemCount: rows.length,
            itemBuilder: (context, index) => _cartao(rows[index]),
          ),
        ),
        if (rodape) SliverToBoxAdapter(child: _rodape()),
      ],
    );
  }

  Widget _cartao(Map<String, dynamic> command) {
    final id = '${command['id'] ?? ''}';
    return ComandaCard(
      command: command,
      sending: widget.gateway.pendingFor(id).length,
      failed: widget.gateway.failedFor(id).length,
      onTap: () => widget.onOpen(command),
    );
  }

  /// O fim da grade: a próxima página chegando, ou por que ela não veio.
  Widget _rodape() => Padding(
    padding: const EdgeInsets.only(bottom: 32),
    child: Center(
      child: _p.error != null
          ? TextButton.icon(
              onPressed: _p.tentarDeNovo,
              icon: const Icon(Icons.refresh),
              label: const Text('Falhou. Tocar para tentar de novo'),
            )
          : const SizedBox.square(
              dimension: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
    ),
  );
}
