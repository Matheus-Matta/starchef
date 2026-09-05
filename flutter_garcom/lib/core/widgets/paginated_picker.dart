import 'dart:async';

import 'package:flutter/material.dart';

import '../network/resource_page.dart';
import '../theme/app_theme.dart';
import 'shadcn_layout.dart';

/// Busca uma página de resultados — a assinatura que o repositório já expõe.
typedef PageFetcher = Future<ResourcePage> Function(int page, String search);

/// Lista com busca e carregamento por rolagem.
///
/// Existe para o app não baixar o cardápio inteiro (ou todas as comandas) para
/// escolher um item: em loja com catálogo grande isso trava a abertura da tela
/// e gasta dados do celular à toa. Carrega a primeira página, e vai buscando o
/// resto conforme o garçom rola.
class PaginatedPicker extends StatefulWidget {
  const PaginatedPicker({
    super.key,
    required this.fetch,
    required this.itemBuilder,
    required this.searchHint,
    this.emptyMessage = 'Nada encontrado.',
  });

  final PageFetcher fetch;
  final Widget Function(BuildContext context, Map<String, dynamic> row)
  itemBuilder;
  final String searchHint;
  final String emptyMessage;

  @override
  State<PaginatedPicker> createState() => _PaginatedPickerState();
}

class _PaginatedPickerState extends State<PaginatedPicker> {
  final _rows = <Map<String, dynamic>>[];
  final _scroll = ScrollController();
  final _search = TextEditingController();

  Timer? _debounce;
  int _page = 1;
  bool _hasMore = true;
  bool _loading = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(_onScroll);
    _load(reset: true);
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _scroll.dispose();
    _search.dispose();
    super.dispose();
  }

  void _onScroll() {
    // Dispara antes de bater no fim: a próxima página costuma chegar enquanto
    // o dedo ainda está rolando, e a lista não "pula".
    if (!_scroll.hasClients || _loading || !_hasMore) return;
    final left = _scroll.position.maxScrollExtent - _scroll.position.pixels;
    if (left < 400) _load();
  }

  /// Busca digitada espera o operador parar: um pedido por tecla afogaria o
  /// caixa e devolveria as respostas fora de ordem.
  void _onSearchChanged(String _) {
    _debounce?.cancel();
    _debounce = Timer(
      const Duration(milliseconds: 350),
      () => _load(reset: true),
    );
  }

  Future<void> _load({bool reset = false}) async {
    if (_loading) return;
    setState(() {
      _loading = true;
      _error = null;
      if (reset) {
        _page = 1;
        _hasMore = true;
        _rows.clear();
      }
    });
    try {
      final page = await widget.fetch(_page, _search.text);
      if (!mounted) return;
      setState(() {
        _rows.addAll(page.rows);
        _hasMore = page.hasMore;
        _page += 1;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = '$error';
        _loading = false;
        _hasMore = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
          child: TextField(
            controller: _search,
            autofocus: true,
            textInputAction: TextInputAction.search,
            onChanged: _onSearchChanged,
            onSubmitted: (_) => _load(reset: true),
            decoration: InputDecoration(
              hintText: widget.searchHint,
              // Sem rótulo, então também sem o espaço que ele reservaria
              // acima da caixa (o tema flutua o rótulo por padrão).
              floatingLabelBehavior: FloatingLabelBehavior.auto,
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _search.text.isEmpty
                  ? null
                  : IconButton(
                      icon: const Icon(Icons.close),
                      onPressed: () {
                        _search.clear();
                        _load(reset: true);
                      },
                    ),
            ),
          ),
        ),
        Expanded(
          child: Container(
            // Fundo próprio atrás da lista: os cartões ficam em `surface` e o
            // contraste separa item de item sem precisar de linha divisória.
            color: scheme.surfaceContainerHighest.withValues(alpha: .45),
            child: _buildList(scheme),
          ),
        ),
      ],
    );
  }

  Widget _buildList(ColorScheme scheme) {
    if (_rows.isEmpty && _loading) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_rows.isEmpty) {
      return AppEmptyState(
        icon: _error == null ? Icons.search_off : Icons.wifi_off,
        title: _error == null ? 'Nada encontrado' : 'Falha na busca',
        description: _error ?? widget.emptyMessage,
      );
    }
    return ListView.separated(
      controller: _scroll,
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      itemCount: _rows.length + (_hasMore || _error != null ? 1 : 0),
      separatorBuilder: (_, _) => const SizedBox(height: AppTheme.gapTight),
      itemBuilder: (context, index) => index >= _rows.length
          ? _Footer(error: _error)
          : widget.itemBuilder(context, _rows[index]),
    );
  }
}

/// Última linha da lista: o carregamento da próxima página, ou o motivo de ela
/// não ter vindo.
class _Footer extends StatelessWidget {
  const _Footer({this.error});

  final String? error;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: AppTheme.gapLoose),
    child: Center(
      child: error != null
          ? Text(
              error!,
              textAlign: TextAlign.center,
              style: TextStyle(
                color: Theme.of(context).colorScheme.error,
                fontSize: 12,
              ),
            )
          : const SizedBox.square(
              dimension: 22,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
    ),
  );
}
