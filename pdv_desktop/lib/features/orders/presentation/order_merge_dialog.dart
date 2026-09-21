import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/app_dialog.dart';
import '../data/order_merge_repository.dart';
import 'order_merge_panels.dart';
import 'order_merge_refund_dialog.dart';

/// Montar a conta de várias comandas, sem sair da tela de venda.
///
/// Fica num diálogo próprio, e não numa aba da tela principal, por duas
/// razões práticas: a conta agrupada tem um ciclo de vida inteiro (abrir →
/// incluir → confirmar → receber) e o operador precisa voltar exatamente para
/// onde estava quando terminar.
///
/// Devolve o **id do pedido de destino** quando a conta é confirmada — é ele
/// que a tela de venda abre para receber. `null` quando o operador desiste.
///
/// Com [orderId], ABRE uma conta nova usando aquela comanda como primeira
/// origem. Com [mergeId], abre uma conta que já existe — é por aqui que o caixa
/// chega numa venda já paga para estorná-la.
Future<String?> showOrderMergeDialog(
  BuildContext context, {
  required OrderMergeRepository repository,
  String? orderId,
  String? mergeId,
}) {
  assert(
    (orderId == null) != (mergeId == null),
    'Informe o pedido (abrir conta nova) OU a consolidação (abrir existente).',
  );
  return showDialog<String>(
    context: context,
    barrierDismissible: false,
    builder: (_) => _OrderMergeDialog(
      repository: repository,
      orderId: orderId,
      mergeId: mergeId,
    ),
  );
}

class _OrderMergeDialog extends StatefulWidget {
  const _OrderMergeDialog({
    required this.repository,
    this.orderId,
    this.mergeId,
  });

  final OrderMergeRepository repository;
  final String? orderId;
  final String? mergeId;

  @override
  State<_OrderMergeDialog> createState() => _OrderMergeDialogState();
}

class _OrderMergeDialogState extends State<_OrderMergeDialog> {
  final _scanner = TextEditingController();
  final _scannerFocus = FocusNode();

  Map<String, dynamic>? _merge;
  bool _busy = false;
  String _error = '';

  /// Conflito (409) não é erro de digitação.
  ///
  /// O servidor responde 409 quando outro caixa chegou antes ou quando o
  /// estado mudou embaixo da tela. Tentar de novo com o mesmo cartão nunca
  /// resolve, e a tela não pode sugerir que sim.
  bool _conflict = false;

  @override
  void initState() {
    super.initState();
    final existente = widget.mergeId;
    _run(
      () => existente != null
          ? widget.repository.load(existente)
          : widget.repository.open(widget.orderId!),
    );
  }

  @override
  void dispose() {
    _scanner.dispose();
    _scannerFocus.dispose();
    super.dispose();
  }

  bool get _isOpen => _merge?['status'] == 'open';
  bool get _isConfirmed => _merge?['status'] == 'confirmed';
  bool get _isPaid => _merge?['status'] == 'paid';
  String get _targetOrderId => '${_merge?['target_order'] ?? ''}';

  Future<void> _run(Future<Map<String, dynamic>> Function() acao) async {
    setState(() {
      _busy = true;
      _error = '';
      _conflict = false;
    });
    try {
      final resultado = await acao();
      if (!mounted) return;
      setState(() => _merge = resultado);
    } on ApiException catch (erro) {
      if (!mounted) return;
      setState(() {
        _error = erro.message;
        _conflict = erro.statusCode == 409;
      });
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        // O foco volta para o campo do leitor: sem isso, o segundo cartão da
        // mesa é bipado em lugar nenhum e o operador só descobre quando olha
        // a tela — que é justamente o que ele não faz enquanto passa cartões.
        _scannerFocus.requestFocus();
      }
    }
  }

  void _scan() {
    final lido = _scanner.text.trim();
    if (lido.isEmpty || _merge == null) return;
    _scanner.clear();
    _run(() => widget.repository.addCommand('${_merge!['id']}', lido));
  }

  void _remove(String commandId) {
    if (_merge == null) return;
    _run(() => widget.repository.removeCommand('${_merge!['id']}', commandId));
  }

  /// Conferência de UMA comanda. Não mexe na conta, então não passa por `_run`:
  /// o resumo na tela continua sendo o mesmo.
  Future<void> _receipt(String commandId) async {
    setState(() {
      _busy = true;
      _error = '';
    });
    try {
      await widget.repository.commandReceipt(commandId);
      if (mounted) {
        setState(() => _error = 'Conferência enviada para a impressora.');
      }
    } on ApiException catch (erro) {
      if (mounted) setState(() => _error = erro.message);
    } finally {
      if (mounted) setState(() => _busy = false);
      _scannerFocus.requestFocus();
    }
  }

  /// Estorna a venda JÁ PAGA.
  ///
  /// O aviso é em texto, e não só um "tem certeza?": o operador precisa ler que
  /// um cartão já reentregue vai ter o pedido do próximo cliente cancelado
  /// junto. É a consequência que não se descobre clicando.
  Future<void> _refund() async {
    if (_merge == null) return;
    final motivo = await showMergeRefundDialog(context);
    if (motivo == null || motivo.isEmpty || !mounted) return;
    await _run(() => widget.repository.refund('${_merge!['id']}', reason: motivo));
    if (!mounted || _error.isNotEmpty) return;
    Navigator.of(context).pop();
  }

  Future<void> _confirm() async {
    if (_merge == null) return;
    await _run(() => widget.repository.confirm('${_merge!['id']}'));
    if (!mounted || !_isConfirmed) return;
    Navigator.of(context).pop(_targetOrderId);
  }

  Future<void> _discard() async {
    if (_merge == null) {
      Navigator.of(context).pop();
      return;
    }
    if (_isPaid) {
      // Numa conta paga, "sair" é só sair: desfazer aqui recusaria no servidor
      // e o operador leria um erro que ele não causou.
      Navigator.of(context).pop();
      return;
    }
    await _run(
      () => widget.repository.cancel('${_merge!['id']}', reason: 'Desfeita no PDV'),
    );
    if (!mounted) return;
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final grupos = _merge == null
        ? const <MergeCommandGroup>[]
        : groupMergeItems(_merge!);
    return AppDialog(
      maxWidth: 1040,
      title: const Text('Conta agrupada de comandas'),
      content: SizedBox(
        height: 520,
        child: Focus(
          // ESC desiste; o resto do teclado é do campo do leitor. O PDV é
          // operado sem mouse, e uma tela que exija o mouse para sair é uma
          // tela que trava o caixa.
          onKeyEvent: (_, evento) {
            if (evento is KeyDownEvent &&
                evento.logicalKey == LogicalKeyboardKey.escape) {
              _discard();
              return KeyEventResult.handled;
            }
            return KeyEventResult.ignored;
          },
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (_error.isNotEmpty)
                MergeErrorBanner(message: _error, conflict: _conflict),
              if (_isOpen)
                MergeScannerField(
                  controller: _scanner,
                  focusNode: _scannerFocus,
                  enabled: !_busy,
                  onSubmit: _scan,
                )
              else if (_isPaid)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Conta paga. Corrigir agora exige o estorno auditado, que '
                    'desfaz caixa, estoque e nota e esvazia todas as comandas.',
                  ),
                )
              else if (_isConfirmed)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 8),
                  child: Text(
                    'Conta confirmada. Para corrigir um item, desfaça a '
                    'consolidação antes de receber.',
                  ),
                ),
              const SizedBox(height: 12),
              Expanded(
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Expanded(
                      child: MergeGroupList(
                        groups: grupos,
                        removable: _isOpen && grupos.length > 1,
                        enabled: !_busy,
                        onRemove: _remove,
                        onReceipt: _receipt,
                      ),
                    ),
                    const SizedBox(width: 16),
                    SizedBox(
                      width: 280,
                      child: MergeSummaryPanel(merge: _merge),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      actions: [
        if (_isPaid)
          // Estornar NÃO é desfazer: aqui já entrou dinheiro, e a operação
          // cancela os pedidos de cartões reentregues.
          TextButton(
            onPressed: _busy ? null : _refund,
            child: const Text('Estornar venda'),
          )
        else
          TextButton(
            onPressed: _busy ? null : _discard,
            child: const Text('Desfazer'),
          ),
        FilledButton(
          onPressed: (_busy || !_isOpen || grupos.isEmpty) ? null : _confirm,
          child: const Text('Confirmar conta'),
        ),
      ],
    );
  }
}
