import 'package:flutter/material.dart';

import '../../../core/network/api_exception.dart';
import '../data/command_repository.dart';
import '../data/linhas_da_comanda.dart';
import 'escolher_produto_da_linha_dialog.dart';
import 'linhas_da_comanda_acoes.dart';
import 'linha_da_comanda_tile.dart';

/// Abre o editor. Salvar fecha o diálogo; erro de gravação aparece dentro dele.
Future<void> abrirLinhasDaComanda(
  BuildContext context,
  CommandRepository comandas, {
  required String restaurantId,
  required List<Map<String, dynamic>> produtos,
}) async {
  await showDialog<bool>(
    context: context,
    builder: (_) => LinhasDaComandaDialog(
      repositorio: LinhasDaComandaRepository(comandas),
      restaurantId: restaurantId,
      produtos: produtos,
    ),
  );
}

/// Edita as linhas que a comanda da Balança Rápida imprime abaixo do peso.
///
/// "Adicionar item" põe um produto (bebida, sobremesa...); "Adicionar linha
/// em branco" põe um traço para escrever à mão o que não está na lista. As em
/// branco ficam sempre no fim, como saem no papel. Devolve `true` ao salvar.
class LinhasDaComandaDialog extends StatefulWidget {
  const LinhasDaComandaDialog({
    super.key,
    required this.repositorio,
    required this.restaurantId,
    required this.produtos,
  });

  final LinhasDaComandaRepository repositorio;
  final String restaurantId;
  final List<Map<String, dynamic>> produtos;

  @override
  State<LinhasDaComandaDialog> createState() => _LinhasDaComandaDialogState();
}

class _LinhasDaComandaDialogState extends State<LinhasDaComandaDialog> {
  List<LinhaDaComanda> _linhas = const [];
  bool _carregando = true;
  bool _salvando = false;
  String _erro = '';

  late final Map<String, String> _nomes = {
    for (final p in widget.produtos) '${p['id']}': '${p['name'] ?? ''}',
  };

  bool get _cheia => _linhas.length >= maximoDeLinhasDaComanda;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    try {
      final linhas = await widget.repositorio.carregar(widget.restaurantId);
      if (mounted) setState(() => _linhas = linhas);
    } on ApiException catch (falha) {
      if (mounted) setState(() => _erro = falha.message);
    } finally {
      if (mounted) setState(() => _carregando = false);
    }
  }

  void _mudar(List<LinhaDaComanda> linhas) =>
      setState(() => _linhas = emOrdemDeImpressao(linhas));

  Future<void> _adicionarItem() async {
    final id = await showDialog<String>(
      context: context,
      builder: (_) => EscolherProdutoDaLinhaDialog(
        produtos: widget.produtos,
        jaEscolhidos: {for (final l in _linhas) ?l.produtoId},
      ),
    );
    if (id != null && mounted) _mudar([..._linhas, LinhaDaComanda.produto(id)]);
  }

  Future<void> _adicionarTitulo() async {
    final nome = await pedirTituloDaLinha(context);
    if (nome == null || !mounted) return;
    _mudar([..._linhas, LinhaDaComanda.titulo(nome)]);
  }

  void _mover(int de, int para) {
    final linhas = [..._linhas];
    linhas.insert(para, linhas.removeAt(de));
    _mudar(linhas);
  }

  Future<void> _salvar() async {
    setState(() {
      _salvando = true;
      _erro = '';
    });
    try {
      await widget.repositorio.salvar(widget.restaurantId, _linhas);
      if (mounted) Navigator.of(context).pop(true);
    } on ApiException catch (falha) {
      if (mounted) setState(() => _erro = falha.message);
    } finally {
      if (mounted) setState(() => _salvando = false);
    }
  }

  Widget _linha(int i) {
    final linha = _linhas[i];
    final produtos = _linhas.where((l) => !l.emBranco).length;
    return LinhaDaComandaTile(
      nome: linha.emBranco
          ? null
          : linha.titulo ??
                _nomes[linha.produtoId] ??
                'Produto fora do cardápio (não sai)',
      onSubir: !linha.emBranco && i > 0 ? () => _mover(i, i - 1) : null,
      onDescer: !linha.emBranco && i < produtos - 1
          ? () => _mover(i, i + 1)
          : null,
      onRemover: () => _mudar([..._linhas]..removeAt(i)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return AlertDialog(
      title: const Text('Linhas da comanda da balança'),
      content: SizedBox(
        width: 560,
        height: 460,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Saem na comanda da pesagem, abaixo do produto, preço do kg, '
              'peso e valor. Vale para todas as balanças do restaurante.',
              style: TextStyle(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 12),
            AcoesDasLinhas(
              onItem: _carregando || _cheia ? null : _adicionarItem,
              onTitulo: _carregando || _cheia ? null : _adicionarTitulo,
              onEmBranco: _carregando || _cheia
                  ? null
                  : () => _mudar([..._linhas, const LinhaDaComanda.emBranco()]),
            ),
            const Divider(height: 24),
            Expanded(
              child: _carregando
                  ? const Center(child: CircularProgressIndicator())
                  : _linhas.isEmpty
                  ? Center(
                      child: Text(
                        'Nenhuma linha: a comanda sai só com a pesagem.',
                        style: TextStyle(color: scheme.onSurfaceVariant),
                      ),
                    )
                  : ListView.builder(
                      itemCount: _linhas.length,
                      itemBuilder: (_, i) => _linha(i),
                    ),
            ),
            if (_erro.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_erro, style: TextStyle(color: scheme.error)),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _salvando ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancelar'),
        ),
        FilledButton.icon(
          onPressed: _carregando || _salvando ? null : _salvar,
          icon: const Icon(Icons.save_rounded),
          label: const Text('Salvar'),
        ),
      ],
    );
  }
}
