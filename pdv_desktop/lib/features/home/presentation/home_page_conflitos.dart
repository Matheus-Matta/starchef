part of 'home_page.dart';

/// Quando o servidor recusa dizendo ONDE está o que o caixa procura, o PDV vai
/// até lá em vez de mostrar um erro.
///
/// "A comanda 15 já está na conta #42" e "nada a cobrar" deixavam o caixa
/// procurando a conta na lista, com o cliente esperando. A recusa agora traz o
/// código e o pedido (`backend/apps/orders/conflitos.py`), e a tela:
///
/// * `comanda_em_outra_conta` → abre a conta #42 — com os itens que o caixa
///   tinha passado no rascunho acrescentados a ela, num envio só;
/// * `comanda_ja_cobrada` / `pedido_ja_pago` → abre o pedido pago (com
///   itens novos no rascunho, só tira a comanda paga dele e segue);
/// * `total_mudou` → recalcula sozinha e explica onde o resto foi cobrado.
///
/// Recusa sem código continua sendo o erro de sempre.
mixin _ConflitosSection on _HomePageShared {
  // ── fornecido por `_HomePageState` ──────────────────────────────────────
  Map<String, dynamic>? get activeOrder;
  Future<void> _editOrder(Map<String, dynamic> order);

  /// `_work` que tenta resolver a recusa antes de mostrá-la como erro.
  @override
  Future<T?> _workResolvendo<T>(
    Future<T> Function() action, {
    required String errorTitle,
    bool fica = false,
  }) async {
    Object? falha;
    final resultado = await _work(
      action,
      errorTitle: errorTitle,
      onError: (erro) => falha = erro,
    );
    final recusa = falha;
    if (resultado == null && recusa != null && mounted) {
      if (!await _resolverConflito(recusa)) {
        _error(recusa, title: errorTitle, fica: fica);
      }
    }
    return resultado;
  }

  /// Resolve a recusa indo ao lugar certo. `false` = não era caso disso.
  ///
  /// A DECISÃO é de `ConflitoDaVenda.decidir` (testada); aqui só se executa.
  Future<bool> _resolverConflito(Object erro) async {
    final conflito = ConflitoDaVenda.decidir(
      erro,
      temLinhasNovas: draft.lines.isNotEmpty,
    );
    final numero = conflito.numero;
    switch (conflito.acao) {
      case AcaoDoConflito.nenhuma:
        return false;
      case AcaoDoConflito.abrirConta:
        final comItens = draft.lines.isNotEmpty;
        if (!await _levarRascunhoPara(conflito.pedidoId!)) return false;
        await _abrirComAviso(
          conflito.pedidoId!,
          comItens
              ? 'A comanda já estava na conta #$numero — abri ela e '
                    'acrescentei os itens que você passou.'
              : 'A comanda já estava na conta #$numero — abri ela para você.',
        );
      case AcaoDoConflito.abrirPago:
        await _abrirComAviso(
          conflito.pedidoId!,
          'Esta comanda já foi paga no pedido #$numero. Abri o pedido pago — '
          'use Reimprimir se precisar do comprovante.',
        );
      case AcaoDoConflito.tirarComandaPaga:
        // Itens novos no rascunho: não se perde o que o caixa passou. A
        // comanda paga sai desta venda, e ela segue com o resto.
        setState(() {
          _desfazerSimulacao();
          draft.commands.clear();
          draft.commandItems.clear();
        });
        _aviso(
          'Esta comanda já foi paga no pedido #$numero — tirei ela desta '
          'venda. Os itens que você passou continuam aqui.',
        );
      case AcaoDoConflito.recalcular:
        draft.anotacoesVistas = null;
        await _simularVenda();
        final onde = conflito.ondeCobrou;
        _aviso(
          '${(erro as ApiException).message}'
          '${onde.isEmpty ? '' : ' Parte da comanda foi cobrada em ${onde.join(', ')}.'}'
          ' A tela já mostra o valor novo.',
        );
    }
    return true;
  }

  /// Leva as linhas novas do rascunho para a conta que já existe — num envio.
  Future<bool> _levarRascunhoPara(String pedidoId) async {
    if (draft.lines.isEmpty) return true;
    try {
      await api.post(
        OrderDraftMaterializer.caminho,
        body: {
          'id': pedidoId,
          'restaurant': restaurantId,
          'items': [for (final linha in draft.lines) linha.toItemPayload()],
        },
        accessToken: token,
      );
      return true;
    } on ApiException {
      return false; // o erro original aparece; o rascunho fica intacto
    }
  }

  Future<void> _abrirComAviso(String pedidoId, String texto) async {
    setState(() {
      _desfazerSimulacao();
      draft.clear();
    });
    await _editOrder({'id': pedidoId});
    if (mounted) _aviso(texto);
  }

  /// Um recado, não um erro: o que o PDV fez sozinho, em uma linha.
  void _aviso(String texto) {
    ScaffoldMessenger.maybeOf(context)?.showSnackBar(
      SnackBar(content: Text(texto), duration: const Duration(seconds: 8)),
    );
  }
}
