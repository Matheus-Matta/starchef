import 'package:flutter/material.dart';

import '../../../core/errors/failure_text.dart';
import '../../../core/widgets/app_page.dart';
import '../../../core/widgets/app_toast.dart';
import '../../menu/presentation/product_picker_sheet.dart';
import '../data/orders_repository.dart';
import 'order_dialogs.dart';
import 'order_formatters.dart';
import 'command_actions_bar.dart';
import 'order_item_tiles.dart';

/// O cartão aberto no aplicativo do garçom.
///
/// A comanda é um bloco de notas: ela anota o consumo e manda para a produção,
/// sem pedido nenhum. Cobrar é gesto do caixa — e é por isso que esta tela
/// **não tem pagamento**, ao contrário da do pedido.
///
/// Fora isso ela é a mesma coisa: a lista de itens, o botão de acrescentar e o
/// de enviar à cozinha. Os cartões de item são os MESMOS widgets do pedido —
/// quem alterna entre as duas telas no turno não deve reaprender nada.
class CommandDetailPage extends StatefulWidget {
  const CommandDetailPage({
    super.key,
    required this.repository,
    required this.command,
  });

  final OrdersRepository repository;
  final Map<String, dynamic> command;

  @override
  State<CommandDetailPage> createState() => _CommandDetailPageState();
}

class _CommandDetailPageState extends State<CommandDetailPage> {
  List<Map<String, dynamic>> _itens = const [];
  bool _carregando = true;
  bool _trabalhando = false;
  String _erro = '';

  String get _id => '${widget.command['id'] ?? ''}';

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() {
      _carregando = true;
      _erro = '';
    });
    try {
      final dados = await widget.repository.commandItems(_id);
      if (!mounted) return;
      final bruto = dados['items'];
      setState(() {
        _itens = bruto is List
            ? bruto
                  .whereType<Map>()
                  .map((item) => Map<String, dynamic>.from(item))
                  .toList()
            : const [];
      });
    } catch (erro) {
      if (mounted) setState(() => _erro = describeFailure(erro));
    } finally {
      if (mounted) setState(() => _carregando = false);
    }
  }

  /// Há o que mandar para a produção?
  ///
  /// Só o item que ainda NÃO foi: reenviar o que a cozinha já recebeu faria o
  /// prato sair duas vezes.
  bool get _temPendenteDeCozinha =>
      _itens.any((item) => fieldText(item['status']) == 'pending');

  double get _total => _itens.fold(
    0,
    (soma, item) => soma + (num.tryParse('${item['total_price'] ?? 0}') ?? 0),
  );

  Future<void> _acrescentar() async {
    final escolha = await showProductPicker(context, widget.repository);
    if (escolha == null || !mounted) return;
    await _trabalhar(
      () => widget.repository.launchCommandItem(
        commandId: _id,
        productId: escolha.productId,
        productName: escolha.productName,
        quantity: escolha.quantity,
        variationId: escolha.variationId,
        addonIds: escolha.addonIds,
        customerNote: escolha.note,
      ),
    );
  }

  Future<void> _enviarACozinha() =>
      _trabalhar(() => widget.repository.sendCommandToKitchen(_id));

  Future<void> _cancelar(Map<String, dynamic> item) async {
    final rotulo = fieldText(item['product_name']);
    // Cancelamento pede motivo e deixa registro — e o item que já foi para a
    // produção avisa antes, porque sai um cupom na impressora do setor.
    final motivo = await askVoidReason(context, item);
    if (motivo == null || !mounted) return;
    await _trabalhar(
      () => widget.repository.voidCommandItem(
        commandId: _id,
        itemId: '${item['id']}',
        itemLabel: rotulo,
        reason: motivo,
      ),
    );
  }

  /// Executa e RELÊ. A anotação pode ter ido para a fila offline, e a lista
  /// precisa mostrar o que o servidor tem — não o que a tela supôs.
  Future<void> _trabalhar(Future<void> Function() acao) async {
    setState(() => _trabalhando = true);
    try {
      await acao();
      await _carregar();
    } catch (erro) {
      if (mounted) showToast(context, describeFailure(erro));
    } finally {
      if (mounted) setState(() => _trabalhando = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final numero = widget.command['number'];
    final mesa = widget.command['current_table_number'];
    return AppPageScaffold(
      title: mesa == null ? 'Comanda $numero' : 'Comanda $numero · Mesa $mesa',
      bottomBar: _acoes(),
      body: _corpo(),
    );
  }

  Widget _corpo() {
    if (_carregando) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_erro.isNotEmpty) {
      return Center(child: Padding(padding: const EdgeInsets.all(24), child: Text(_erro)));
    }
    if (_itens.isEmpty) {
      // Cartão livre mostra VAZIO, e não o consumo de quem o usou antes: o
      // histórico continua existindo, mas não é o que o garçom pergunta aqui.
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'Nada lançado nesta comanda.\nToque em acrescentar.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.builder(
        itemCount: _itens.length,
        itemBuilder: (_, indice) => OrderItemTile(
          item: _itens[indice],
          onVoid: _trabalhando ? null : () => _cancelar(_itens[indice]),
        ),
      ),
    );
  }

  Widget _acoes() => CommandActionsBar(
    total: _total,
    busy: _trabalhando,
    canSend: _temPendenteDeCozinha,
    onAdd: _acrescentar,
    onSend: _enviarACozinha,
  );
}
