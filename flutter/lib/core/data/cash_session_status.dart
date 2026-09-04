/// Estados de uma sessão de caixa — os mesmos nomes que o backend usa.
///
/// Esta lista existia duplicada e divergente: aqui o fechamento com diferença
/// era gravado como `closed_difference`, e no backend ele é
/// `closed_with_difference`. O efeito prático era grave — um caixa já fechado
/// continuava "não finalizado" para o terminal offline, e a tela seguia
/// oferecendo sangria, suprimento e fechamento de uma sessão que não existia
/// mais. Um ponto único de verdade é o que impede a divergência de voltar.
abstract final class CashSessionStatus {
  static const open = 'open';
  static const pendingApproval = 'pending_manager_approval';
  static const closed = 'closed';
  static const closedWithDifference = 'closed_with_difference';
  static const cancelled = 'cancelled';

  /// Estados TERMINAIS: a sessão acabou e o caixa está livre.
  static const finished = {closed, closedWithDifference, cancelled};

  /// Grafias antigas que ainda podem estar gravadas no SQLite deste terminal.
  ///
  /// Sem isto, uma sessão fechada antes desta correção continuaria bloqueando
  /// a abertura do caixa (e aparecendo como aberta) até alguém limpar a base.
  static const _legacyFinished = {'closed_difference'};

  /// A sessão acabou?
  static bool isFinished(Object? status) {
    final value = '${status ?? ''}';
    return finished.contains(value) || _legacyFinished.contains(value);
  }

  /// Normaliza uma grafia antiga para o nome que o backend reconhece.
  static String normalize(Object? status) {
    final value = '${status ?? ''}';
    return _legacyFinished.contains(value) ? closedWithDifference : value;
  }
}
