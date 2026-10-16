import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/formatters/value_formatters.dart';
import '../data/historico_de_passagens.dart';

/// As últimas passagens, para reimprimir — feito para TECLADO.
///
/// Abre com Tab na estação. ↑ ↓ andam, Enter reimprime a marcada, Esc fecha.
/// As setas só são capturadas AQUI (e na escolha do produto): fora dos
/// modais, a tela da balança não prende tecla nenhuma de navegação.
/// Devolve a passagem escolhida, ou `null`.
class HistoricoDePassagensDialog extends StatefulWidget {
  const HistoricoDePassagensDialog({super.key, required this.passagens});

  final List<PassagemDaBalanca> passagens;

  @override
  State<HistoricoDePassagensDialog> createState() => _HistoricoState();
}

class _HistoricoState extends State<HistoricoDePassagensDialog> {
  static const _alturaDaLinha = 64.0;
  final _rolagem = ScrollController();
  int _indice = 0;

  @override
  void dispose() {
    _rolagem.dispose();
    super.dispose();
  }

  void _mover(int passo) {
    if (widget.passagens.isEmpty) return;
    setState(() {
      _indice = (_indice + passo).clamp(0, widget.passagens.length - 1);
    });
    if (!_rolagem.hasClients) return;
    final topo = _indice * _alturaDaLinha;
    final visivel = _rolagem.position.viewportDimension;
    if (topo < _rolagem.offset) {
      _rolagem.jumpTo(topo);
    } else if (topo + _alturaDaLinha > _rolagem.offset + visivel) {
      _rolagem.jumpTo(topo + _alturaDaLinha - visivel);
    }
  }

  void _escolher(int indice) {
    if (indice >= widget.passagens.length) return;
    final passagem = widget.passagens[indice];
    if (passagem.reimprimivel) Navigator.of(context).pop(passagem);
  }

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
    } else if (tecla == LogicalKeyboardKey.escape ||
        tecla == LogicalKeyboardKey.tab) {
      Navigator.of(context).pop();
    } else {
      return KeyEventResult.ignored;
    }
    return KeyEventResult.handled;
  }

  Widget _linha(BuildContext context, int i) {
    final p = widget.passagens[i];
    final hora = TimeOfDay.fromDateTime(p.quando).format(context);
    return SizedBox(
      height: _alturaDaLinha,
      child: ListTile(
        selected: i == _indice,
        selectedTileColor: Theme.of(context).colorScheme.primaryContainer,
        enabled: p.reimprimivel,
        leading: Text(
          p.comanda,
          style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900),
        ),
        title: Text(
          p.produto,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w700),
        ),
        subtitle: Text(
          '$hora · ${p.pesoKg.toStringAsFixed(3)} kg'
          '${p.reimprimivel ? '' : ' · sem etiqueta'}',
        ),
        trailing: Text(
          ValueFormatters.money(p.total),
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
      title: const Text('Últimas passagens'),
      content: SizedBox(
        width: 560,
        height: _alturaDaLinha * 7,
        child: widget.passagens.isEmpty
            ? const Center(
                child: Text('Nenhuma passagem neste terminal ainda.'),
              )
            : ListView.builder(
                controller: _rolagem,
                itemExtent: _alturaDaLinha,
                itemCount: widget.passagens.length,
                itemBuilder: _linha,
              ),
      ),
      actions: [
        Text(
          '↑ ↓ escolhe · Enter reimprime · Esc fecha',
          style: TextStyle(
            fontSize: 12,
            color: Theme.of(context).colorScheme.onSurfaceVariant,
          ),
        ),
      ],
    ),
  );
}
