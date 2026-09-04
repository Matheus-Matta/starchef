import 'entity_record.dart';

/// Quem vence quando os dois lados alteraram o mesmo registro (§21).
enum ConflictOutcome {
  /// A versão do servidor é gravada por cima.
  ///
  /// Vale tanto para um registro que ninguém alterou aqui quanto para o
  /// retorno da própria entrega — nos dois casos a ação é a mesma, e nomear
  /// dois resultados idênticos só faria o leitor procurar uma diferença que
  /// não existe.
  acceptRemote,

  /// A alteração local ainda não entregue é preservada.
  keepLocal,
}

/// Resolução de conflito entre a cópia local e a versão do servidor.
///
/// A regra é simples e conservadora de propósito: **o que o operador acabou de
/// fazer e ainda não subiu vale mais que a cópia do servidor**. Descartar a
/// alteração local apagaria da tela um item lançado há segundos, que ainda
/// está na fila esperando a rede — e o operador não teria como saber que
/// perdeu o lançamento.
///
/// A exceção é o retorno da própria entrega: quando a operação sobe e o
/// servidor devolve o registro gravado, essa resposta é a verdade — ela já
/// contém o que era local, agora com identificadores e numeração definitivos.
abstract final class ConflictResolver {
  static ConflictOutcome resolve({
    required EntityRecord? local,
    required Map<String, dynamic> remote,
    required bool confirmedByDelivery,
  }) {
    if (confirmedByDelivery) return ConflictOutcome.acceptRemote;
    if (local == null) return ConflictOutcome.acceptRemote;
    if (local.syncStatus == SyncStatus.pending) return ConflictOutcome.keepLocal;
    return ConflictOutcome.acceptRemote;
  }

  /// A versão do servidor é mais nova que a que já está guardada?
  ///
  /// Usado para descartar um evento fora de ordem: com WebSocket e
  /// sincronização periódica correndo juntos, a mesma entidade pode chegar
  /// duas vezes, e a segunda pode ser a mais antiga.
  static bool isStale({
    required EntityRecord? local,
    required Map<String, dynamic> remote,
  }) {
    final stored = local?.serverVersion;
    final incoming = '${remote['updated_at'] ?? ''}';
    if (stored == null || stored.isEmpty || incoming.isEmpty) return false;
    final storedAt = DateTime.tryParse(stored);
    final incomingAt = DateTime.tryParse(incoming);
    if (storedAt == null || incomingAt == null) return false;
    return incomingAt.isBefore(storedAt);
  }
}
