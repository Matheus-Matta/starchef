import '../../../core/network/api_exception.dart';

/// O que fazer com uma recusa do servidor que diz ONDE está o que o caixa
/// procura — decisão pura, executada por `home_page_conflitos.dart`.
///
/// "A comanda 15 já está na conta #42" e "nada a cobrar" deixavam o caixa
/// procurando a conta na lista com o cliente esperando. Com o código e o
/// pedido na recusa (`backend/apps/orders/conflitos.py`), a tela vai até lá.
enum AcaoDoConflito {
  /// Recusa comum: mostrar o erro, como sempre.
  nenhuma,

  /// A comanda está numa conta em aberto: abrir ela (com os itens novos do
  /// rascunho acrescentados, quando houver).
  abrirConta,

  /// A comanda (ou o pedido) já foi paga e o rascunho só tinha ela: abrir o
  /// pedido pago.
  abrirPago,

  /// A comanda já foi paga, mas o caixa passou itens novos: tirar a comanda
  /// da venda e seguir com os itens — nada do que ele passou se perde.
  tirarComandaPaga,

  /// O total mudou entre simular e concluir: recalcular e explicar.
  recalcular,
}

class ConflitoDaVenda {
  const ConflitoDaVenda(
    this.acao, {
    this.pedidoId,
    this.numero,
    this.ondeCobrou = const [],
  });

  final AcaoDoConflito acao;
  final String? pedidoId;
  final Object? numero;

  /// Os pedidos (`#42`) que levaram parte da comanda, no `total_mudou`.
  final List<String> ondeCobrou;

  static const nenhum = ConflitoDaVenda(AcaoDoConflito.nenhuma);

  /// A decisão. `temLinhasNovas` = o rascunho tem itens passados agora.
  static ConflitoDaVenda decidir(Object erro, {required bool temLinhasNovas}) {
    if (erro is! ApiException || erro.code == null) return nenhum;
    final destino = '${erro.data['order_id'] ?? ''}';
    final numero = erro.data['sequence'];
    switch (erro.code) {
      case 'comanda_em_outra_conta' when destino.isNotEmpty:
        return ConflitoDaVenda(
          AcaoDoConflito.abrirConta,
          pedidoId: destino,
          numero: numero,
        );
      case 'comanda_ja_cobrada' || 'pedido_ja_pago' when destino.isNotEmpty:
        return ConflitoDaVenda(
          temLinhasNovas
              ? AcaoDoConflito.tirarComandaPaga
              : AcaoDoConflito.abrirPago,
          pedidoId: destino,
          numero: numero,
        );
      case 'total_mudou':
        return ConflitoDaVenda(
          AcaoDoConflito.recalcular,
          ondeCobrou: [
            for (final conta in erro.data['cobradas_em'] as List? ?? const [])
              if (conta is Map && conta['sequence'] != null)
                '#${conta['sequence']}',
          ],
        );
    }
    return nenhum;
  }
}
