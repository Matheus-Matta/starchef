/// Operações que o PDV sabe concluir sem falar com o servidor na hora.
///
/// Esta lista é consultada em dois lugares distantes: a fila offline do
/// `ApiClient` e o envelope aceito pelo relay entre Caixa Cliente e Caixa
/// Principal. Enquanto ela existia duplicada, as duas divergiram — o cliente
/// passou a enfileirar fechamento e pagamento, o relay continuou recusando, e
/// essas operações acabavam indo do caixa cliente direto para a nuvem,
/// contornando o principal. Manter a decisão em um lugar só é o que impede
/// essa divergência de voltar.
///
/// Só entram aqui operações cujo reenvio é seguro: o backend deduplica pela
/// `Idempotency-Key`, então repetir devolve a resposta original em vez de
/// criar uma segunda venda.
abstract final class OfflineMutations {
  /// Identificador em um caminho que o próprio aplicativo montou.
  ///
  /// Sem `/` e sem `.`, então não há como atravessar diretórios. O tamanho
  /// fica livre: um ID curto vindo do servidor não é motivo para recusar a
  /// operação e deixar o operador sem vender.
  static const _localId = r'[A-Za-z0-9_-]+';

  /// Identificador em um caminho recebido pela rede local.
  ///
  /// Aqui o principal executa o que um cliente pediu, então o formato é
  /// verificado com rigor — inclusive um tamanho mínimo, que descarta de
  /// imediato qualquer coisa que não pareça um identificador real.
  static const _remoteId = r'[A-Za-z0-9_-]{8,160}';

  /// A operação pode esperar em uma fila e ser entregue depois?
  static bool isQueueable(String method, String path) =>
      _matches(method, path, _localId);

  /// A operação pode ser entregue ao Caixa Principal pela LAN?
  ///
  /// É um subconjunto de [isQueueable]: cadastro de cliente não pertence ao
  /// atendimento em curso e não ganha nada em passar pelo principal.
  static bool isRelayable(String method, String path) =>
      !path.startsWith('/customers/') && _matches(method, path, _remoteId);

  /// A operação cria um recurso e precisa de um ID temporário local.
  static bool createsResource(String method, String path) =>
      method == 'POST' &&
      (path == '/customers/' ||
          path == '/orders/' ||
          path == '/orders/open-command/' ||
          RegExp('^/orders/$_localId/items/\$').hasMatch(path) ||
          // Um pagamento tambem cria um recurso. Dar a ele um ID temporario
          // permite reconciliar o recebimento otimista com o Payment real e
          // impede que ele permaneça para sempre como "pendente local".
          RegExp('^/orders/$_localId/pay/\$').hasMatch(path));

  static bool _matches(String method, String path, String id) {
    if (method == 'POST') {
      return path == '/customers/' ||
          path == '/orders/' ||
          // Abrir pedido por comanda entra na fila pelo mesmo motivo da mesa:
          // é o começo do atendimento, e recusar aqui deixaria o operador sem
          // conseguir lançar nada enquanto a rede não volta.
          path == '/orders/open-command/' ||
          RegExp('^/orders/$id/items/\$').hasMatch(path) ||
          // Fechar, mandar para a cozinha e registrar pagamento: o resto do
          // atendimento, para que uma queda de rede não impeça a venda de
          // terminar.
          RegExp('^/orders/$id/(close|send-to-kitchen|pay)/\$').hasMatch(path) ||
          // Vincular/desvincular a mesa é parte de abrir o atendimento na
          // comanda — sem isso o garçom abre o pedido pelo principal e depois
          // esbarra no relay justamente na hora de dizer em que mesa o cliente
          // sentou.
          RegExp('^/commands/$id/(link-table|unlink-table)/\$').hasMatch(path);
    }
    if (method == 'PATCH') return path.startsWith('/customers/');
    if (method == 'DELETE') {
      return RegExp('^/orders/$id/items/$id/void/\$').hasMatch(path);
    }
    return false;
  }
}
