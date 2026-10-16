import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/formatters/value_formatters.dart';

/// "Qual produto é este prato?" — só produtos por quilo, feito para TECLADO.
///
/// ↑ ↓ andam, Enter confirma, 1–9 escolhem direto, Esc cancela. Abre já
/// marcado no último produto usado: no caso comum (o mesmo buffet o dia
/// todo) basta um Enter. Devolve o produto escolhido, ou `null`.
class EscolherProdutoPorQuiloDialog extends StatefulWidget {
  const EscolherProdutoPorQuiloDialog({
    super.key,
    required this.produtos,
    required this.pesoKg,
    this.inicialId,
  });

  final List<Map<String, dynamic>> produtos;
  final double pesoKg;
  final String? inicialId;

  @override
  State<EscolherProdutoPorQuiloDialog> createState() => _EscolherState();
}

class _EscolherState extends State<EscolherProdutoPorQuiloDialog> {
  static const _alturaDaLinha = 60.0;
  final _rolagem = ScrollController();
  late int _indice = widget.produtos
      .indexWhere((p) => '${p['id']}' == widget.inicialId)
      .clamp(0, widget.produtos.length - 1);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _mostrarSelecionado());
  }

  @override
  void dispose() {
    _rolagem.dispose();
    super.dispose();
  }

  void _mover(int passo) {
    setState(() {
      _indice = (_indice + passo).clamp(0, widget.produtos.length - 1);
    });
    _mostrarSelecionado();
  }

  /// Mantém a linha marcada à vista quando a lista é maior que a janela.
  void _mostrarSelecionado() {
    if (!_rolagem.hasClients) return;
    final topo = _indice * _alturaDaLinha;
    final visivel = _rolagem.position.viewportDimension;
    if (topo < _rolagem.offset) {
      _rolagem.jumpTo(topo);
    } else if (topo + _alturaDaLinha > _rolagem.offset + visivel) {
      _rolagem.jumpTo(topo + _alturaDaLinha - visivel);
    }
  }

  void _escolher(int indice) =>
      Navigator.of(context).pop(widget.produtos[indice]);

  KeyEventResult _tecla(FocusNode _, KeyEvent evento) {
    if (evento is KeyUpEvent) return KeyEventResult.ignored;
    final tecla = evento.logicalKey;
    if (tecla == LogicalKeyboardKey.arrowDown) {
      _mover(1);
    } else if (tecla == LogicalKeyboardKey.arrowUp) {
      _mover(-1);
    } else if (tecla == LogicalKeyboardKey.enter ||
        tecla == LogicalKeyboardKey.numpadEnter) {
      _escolher(_indice);
    } else if (tecla == LogicalKeyboardKey.escape) {
      Navigator.of(context).pop();
    } else {
      final numero = int.tryParse(evento.character ?? '');
      if (numero == null || numero < 1 || numero > widget.produtos.length) {
        return KeyEventResult.ignored;
      }
      _escolher(numero - 1);
    }
    return KeyEventResult.handled;
  }

  Widget _linha(BuildContext context, int i) {
    final produto = widget.produtos[i];
    final preco = ValueFormatters.number(produto['current_price']);
    final scheme = Theme.of(context).colorScheme;
    return SizedBox(
      height: _alturaDaLinha,
      child: ListTile(
        selected: i == _indice,
        selectedTileColor: scheme.primaryContainer,
        leading: CircleAvatar(
          radius: 14,
          child: Text(
            i < 9 ? '${i + 1}' : '',
            style: const TextStyle(fontSize: 13),
          ),
        ),
        title: Text(
          '${produto['name'] ?? ''}',
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Text('${ValueFormatters.money(preco)}/kg'),
        trailing: Text(
          ValueFormatters.money(preco * widget.pesoKg),
          style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 16),
        ),
        onTap: () => _escolher(i),
      ),
    );
  }

  @override
  Widget build(BuildContext context) => Focus(
    autofocus: true,
    onKeyEvent: _tecla,
    child: AlertDialog(
      title: Text('Qual produto? ${widget.pesoKg.toStringAsFixed(3)} kg'),
      content: SizedBox(
        width: 520,
        height: (widget.produtos.length * _alturaDaLinha).clamp(
          _alturaDaLinha,
          _alturaDaLinha * 7,
        ),
        child: ListView.builder(
          controller: _rolagem,
          itemExtent: _alturaDaLinha,
          itemCount: widget.produtos.length,
          itemBuilder: _linha,
        ),
      ),
      actions: [
        Text(
          '↑ ↓ escolhe · Enter lança · 1–9 direto · Esc cancela',
          style: TextStyle(
            fontSize: 12,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    ),
  );
}
