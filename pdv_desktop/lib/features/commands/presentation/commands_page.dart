import 'dart:async';

import 'package:flutter/material.dart';

import '../data/command_repository.dart';
import 'command_detail_view.dart';
import 'commands_actions.dart';
import 'commands_grid.dart';
import 'commands_loading.dart';

/// As comandas em DUAS telas: o salão e o cartão aberto.
///
/// **O salão** é uma grade de cartões, como o mapa de mesas — sem catálogo e
/// sem carrinho. É onde o operador chega, e a ordem é a do gesto: primeiro o
/// cliente, depois o que ele pediu.
///
/// **O cartão aberto** é o mesmo desenho da venda: catálogo à esquerda,
/// carrinho à direita. Quem alterna entre esta tela e a de venda durante o
/// turno não deve reaprender onde as coisas estão. O que muda são os botões —
/// aqui **não existe pagamento**, porque a comanda é um bloco de notas. Ela
/// anota e manda para a produção; cobrar é gesto do caixa, no pedido.
///
/// Um cartão EM USO abre com o que ele tem pendente. Um cartão livre abre
/// vazio — e não com o consumo de quem o usou antes, que continua no histórico
/// mas não é o que a tela do atendimento pergunta.
class CommandsPage extends StatefulWidget {
  const CommandsPage({
    super.key,
    required this.repository,
    this.products = const [],
    this.categories = const [],
    this.tables = const [],
    this.restaurantId,
    this.codigosLidos,
  });

  final CommandRepository repository;
  final List<Map<String, dynamic>> products;
  final List<Map<String, dynamic>> categories;

  /// As mesas do salão, para sentar o cartão em uma delas.
  ///
  /// Vêm de fora, do mesmo catálogo que a venda usa: carregar uma segunda
  /// cópia faria as duas divergirem na primeira mesa criada.
  final List<Map<String, dynamic>> tables;
  final String? restaurantId;

  /// Os códigos lidos que a casca captura quando NENHUM campo está focado.
  ///
  /// O campo "Passe o cartão" continua existindo — ele é o caminho de quem
  /// digita. Mas exigir um clique nele antes de cada leitura anula o leitor:
  /// basta o operador ter tocado num produto para a leitura seguinte cair no
  /// vazio.
  final Stream<String>? codigosLidos;

  @override
  State<CommandsPage> createState() => _CommandsPageState();
}

class _CommandsPageState extends State<CommandsPage>
    with CommandsLoading<CommandsPage>, CommandsActions<CommandsPage> {
  final _busca = TextEditingController();
  final _leitor = TextEditingController();
  final _focoDoLeitor = FocusNode();

  String? _categoria;
  String _termoDeProduto = '';

  @override
  CommandRepository get repository => widget.repository;
  @override
  String? get restaurantId => widget.restaurantId;
  @override
  TextEditingController get leitor => _leitor;
  @override
  FocusNode get focoDoLeitor => _focoDoLeitor;
  @override
  Stream<String>? get codigosLidos => widget.codigosLidos;
  @override
  List<Map<String, dynamic>> get mesas => widget.tables;

  @override
  void initState() {
    super.initState();
    carregar();
    ouvirCodigosLidos();
  }

  @override
  void dispose() {
    pararDeOuvirCodigos();
    _busca.dispose();
    _leitor.dispose();
    _focoDoLeitor.dispose();
    super.dispose();
  }

  List<Map<String, dynamic>> get _comandasVisiveis {
    final termo = _busca.text.trim().toLowerCase();
    if (termo.isEmpty) return comandas;
    return comandas
        .where(
          (comanda) => ['number', 'code', 'customer_name']
              .map((campo) => '${comanda[campo] ?? ''}'.toLowerCase())
              .any((valor) => valor.contains(termo)),
        )
        .toList(growable: false);
  }

  List<Map<String, dynamic>> get _produtosVisiveis {
    final termo = _termoDeProduto.trim().toLowerCase();
    return widget.products
        .where((produto) {
          if (_categoria != null && '${produto['category']}' != _categoria) {
            return false;
          }
          if (termo.isEmpty) return true;
          return ['name', 'internal_code', 'ean']
              .map((campo) => '${produto[campo] ?? ''}'.toLowerCase())
              .any((valor) => valor.contains(termo));
        })
        .toList(growable: false);
  }

  /// Volta para o salão. O cartão aberto é fechado, não escondido: reabrir
  /// relê o que ele tem, e outro garçom pode ter lançado nele nesse meio-tempo.
  void _voltarAoSalao() {
    setState(() {
      selecionada = null;
      itens = const [];
      recado = '';
      erro = '';
    });
    unawaited(carregar());
  }

  Future<void> _abrir(Map<String, dynamic> comanda) async {
    setState(() {
      selecionada = comanda;
      recado = '';
      itens = const [];
    });
    await carregarItens();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (erro.isNotEmpty || recado.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(20, 12, 20, 0),
            child: Text(
              erro.isNotEmpty ? erro : recado,
              style: TextStyle(
                color: erro.isNotEmpty ? scheme.error : scheme.primary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        Expanded(child: selecionada == null ? _salao() : _cartaoAberto()),
      ],
    );
  }

  /// A primeira tela: escolher o cartão.
  Widget _salao() => CommandsGrid(
    comandas: _comandasVisiveis,
    carregando: carregando,
    controladorDaBusca: _busca,
    controladorDoLeitor: _leitor,
    focoDoLeitor: _focoDoLeitor,
    onBuscaMudou: () => setState(() {}),
    onLeitura: abrirPorCodigo,
    onAbrir: _abrir,
  );

  /// A segunda: o cartão aberto, no desenho da venda.
  Widget _cartaoAberto() => CommandDetailView(
    comanda: selecionada,
    itens: itens,
    produtos: _produtosVisiveis,
    todosOsProdutos: widget.products,
    categorias: widget.categories,
    categoria: _categoria,
    termoDeProduto: _termoDeProduto,
    carregando: carregandoItens,
    enviando: enviando,
    imprimindo: imprimindo,
    onVoltar: _voltarAoSalao,
    onBuscaDeProduto: (valor) => setState(() => _termoDeProduto = valor),
    onCategoria: (valor) => setState(() => _categoria = valor),
    onProduto: lancar,
    onSendToKitchen: enviarACozinha,
    onPrintReceipt: imprimirRecibo,
    onVoidItem: cancelarItem,
    onEscolherMesa: widget.tables.isEmpty ? null : escolherMesa,
  );
}
