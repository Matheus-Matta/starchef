import 'package:flutter/material.dart';

import '../../../core/widgets/app_sheet.dart';
import '../../../core/widgets/paginated_picker.dart';
import '../../../core/widgets/picker_tile.dart';
import '../../orders/data/orders_repository.dart';
import '../../orders/presentation/order_formatters.dart';
import '../domain/product_options.dart';
import 'category_chips_bar.dart';
import 'product_config_view.dart';
import 'product_thumbnail.dart';
import 'product_price_text.dart';
import 'product_quick_add.dart';

export '../domain/product_options.dart' show ProductChoice;

/// Busca do catálogo (paginada) e, na sequência, a configuração do item.
///
/// Duas etapas na mesma folha: escolher o produto e dizer como ele vai. A
/// altura é fixa de propósito — a lista carrega páginas conforme o garçom
/// rola, e uma folha que cresce a cada página "pula" debaixo do dedo.
///
/// Com [onChoose], o cardápio FICA ABERTO: cada item confirmado entra no
/// pedido e a lista volta com a mesma busca e categoria. Lançar a mesa inteira
/// era abrir, escolher, confirmar, fechar — uma vez por prato. Produto sem
/// variação nem adicional entra com um toque; segurar abre a configuração
/// (quantidade, observação).
Future<ProductChoice?> showProductPicker(
  BuildContext context,
  OrdersRepository repository, {
  Future<void> Function(ProductChoice choice)? onChoose,
}) => showAppSheet<ProductChoice>(
  context,
  heightFactor: .85,
  builder: (context) =>
      ProductPicker(repository: repository, onChoose: onChoose),
);

class ProductPicker extends StatefulWidget {
  const ProductPicker({super.key, required this.repository, this.onChoose});

  final OrdersRepository repository;
  final Future<void> Function(ProductChoice choice)? onChoose;

  @override
  State<ProductPicker> createState() => _ProductPickerState();
}

/// A última categoria escolhida, enquanto o app estiver aberto: o garçom que
/// lança três bebidas seguidas não toca em "Bebidas" três vezes.
String? _ultimaCategoria;

class _ProductPickerState extends State<ProductPicker> {
  Map<String, dynamic>? _selected;
  int _added = 0;
  List<Map<String, dynamic>> _categorias = const [];
  String? _categoria = _ultimaCategoria;

  @override
  void initState() {
    super.initState();
    _carregarCategorias();
  }

  /// Sem as categorias o seletor continua funcionando só com a busca: a
  /// barra é atalho, não caminho obrigatório.
  Future<void> _carregarCategorias() async {
    try {
      final categorias = await widget.repository.productCategories();
      if (!mounted) return;
      setState(() {
        _categorias = categorias;
        // A categoria lembrada pode ter sido desativada desde então.
        if (!categorias.any((c) => '${c['id']}' == _categoria)) {
          _categoria = _ultimaCategoria = null;
        }
      });
    } catch (_) {}
  }

  void _escolherCategoria(String? id) {
    setState(() => _categoria = _ultimaCategoria = id);
  }

  Future<void> _confirm(ProductChoice choice) async {
    final onChoose = widget.onChoose;
    if (onChoose == null) {
      Navigator.of(context).pop(choice);
      return;
    }
    await onChoose(choice);
    if (!mounted) return;
    setState(() {
      _added += choice.quantity;
      _selected = null;
    });
    avisarAdicionado(context, choice);
  }

  void _tap(Map<String, dynamic> product) {
    if (widget.onChoose != null && entraComUmToque(product)) {
      _confirm(escolhaSimples(product));
      return;
    }
    setState(() => _selected = product);
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    // A lista fica VIVA por baixo da configuração: ao voltar, a busca digitada
    // e a rolagem continuam onde estavam.
    return Stack(
      children: [
        Offstage(offstage: selected != null, child: _lista()),
        if (selected != null)
          ProductConfigView(
            product: selected,
            onBack: () => setState(() => _selected = null),
            onConfirm: _confirm,
          ),
      ],
    );
  }

  Widget _lista() {
    return Column(
      children: [
        AppSheetHeader(
          title: 'Adicionar item',
          subtitle: _added > 0 ? '$_added item(ns) adicionado(s)' : null,
          trailing: widget.onChoose == null
              ? null
              : FilledButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: Text(_added > 0 ? 'Concluir' : 'Fechar'),
                ),
        ),
        Expanded(
          child: PaginatedPicker(
            searchHint: 'Buscar produto',
            emptyMessage: 'Nenhum produto encontrado.',
            fetch: _fetch,
            filterKey: _categoria,
            header: _categorias.isEmpty
                ? null
                : Padding(
                    padding: const EdgeInsets.only(bottom: 8),
                    child: CategoryChipsBar(
                      categories: _categorias,
                      selectedId: _categoria,
                      onSelected: _escolherCategoria,
                    ),
                  ),
            itemBuilder: (context, product) => PickerTile(
              title: '${product['name'] ?? ''}',
              subtitle: _subtitle(product),
              leading: ProductThumbnail(product: product),
              trailing: ProductPriceText(product: product),
              onTap: () => _tap(product),
              onLongPress: () => setState(() => _selected = product),
            ),
          ),
        ),
      ],
    );
  }

  /// O filtro é aplicado sobre a página recebida: `hasMore` continua vindo da
  /// API, então a rolagem segue buscando mesmo quando uma página inteira cai
  /// fora (só adicionais, por exemplo).
  Future<ResourcePage> _fetch(int page, String search) async {
    final result = await widget.repository.products(
      page: page,
      search: search,
      categoryId: _categoria,
    );
    return ResourcePage(
      rows: result.rows.where(isSellable).toList(),
      hasMore: result.hasMore,
    );
  }

  static String? _subtitle(Map<String, dynamic> product) {
    final code = fieldText(product['internal_code']);
    final options =
        activeVariations(product).length + activeAddons(product).length;
    final parts = [
      if (code.isNotEmpty) '#$code',
      if (options > 0) '$options opção${options == 1 ? '' : 'ões'}',
    ];
    return parts.isEmpty ? null : parts.join(' · ');
  }
}
