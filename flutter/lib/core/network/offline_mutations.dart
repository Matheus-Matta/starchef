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
/// Não há mais exceção de rota: TUDO o que um secundário escreve passa pelo
/// principal. Cada exceção que existiu aqui era, na prática, um segundo
/// caminho até a nuvem saindo de um terminal que não deveria ter nenhum.
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
  /// Não há exceção: um Caixa Secundário não fala com o servidor, ponto. O
  /// cadastro de cliente já foi exceção aqui — "não pertence ao atendimento em
  /// curso" — mas o resultado prático era um segundo caminho até a nuvem,
  /// saindo de um terminal que não deveria ter nenhum. Um cliente cadastrado
  /// direto na nuvem também demorava a aparecer para os outros caixas, que
  /// leem do principal.
  ///
  /// O conjunto é MAIOR que [isQueueable]: há operações que ninguém pode
  /// guardar numa fila, mas que o principal executa em nome de quem pediu
  /// justamente porque é ele quem alcança a nuvem (ver [_principalOnly]).
  static bool isRelayable(String method, String path) =>
      _matches(method, path, _remoteId) ||
      _principalOnly(method, path, _remoteId) ||
      isScaleCheckout(method, path, _remoteId);

  /// O Caixa Principal sabe executar isto? — pela ótica de quem envia.
  ///
  /// Mesma lista de [isRelayable], mas com o formato de id frouxo: aqui o
  /// caminho foi montado por este próprio aplicativo, e um id curto vindo do
  /// servidor não é motivo para recusar a operação e deixar o operador sem
  /// vender. O rigor de formato vale do outro lado, onde o principal executa
  /// o que chegou pela rede.
  static bool canBeHandledByPrincipal(String method, String path) =>
      _matches(method, path, _localId) ||
      _principalOnly(method, path, _localId) ||
      isScaleCheckout(method, path, _localId);

  /// O Caixa Principal executa isto por um cliente, mas ninguém enfileira.
  ///
  /// Transferir uma sessão de caixa e autorizar uma divergência são decisões
  /// que o servidor precisa validar (gerente, senha do restaurante). Guardá-las
  /// numa fila para aplicar depois seria decidir agora e conferir depois — o
  /// contrário do que uma autorização significa. O secundário as encaminha ao
  /// principal; se nem ele alcançar o servidor, a operação é recusada na hora.
  static bool _principalOnly(String method, String path, String id) =>
      method == 'POST' &&
      RegExp('^/cash-register/$id/(transfer|approve)/\$').hasMatch(path);

  /// Fechamento de uma pesagem na comanda.
  ///
  /// Fica fora de [_matches] de propósito: ele não entra na fila **por conta
  /// do `ApiClient`** — quem o coloca lá é o próprio armazenamento local, ao
  /// montar o pedido da balança com o peso no corpo (o backend materializa a
  /// leitura no replay). Aqui só se declara que o Caixa Principal aceita
  /// recebê-lo pela rede local: sem isso, a balança de um Caixa Secundário
  /// pesava e nunca conseguia fechar a venda.
  static bool isScaleCheckout(String method, String path, [String? id]) =>
      method == 'POST' &&
      RegExp('^/scales/${id ?? _localId}/checkout-command/\$').hasMatch(path);

  /// A operação decide o DONO de uma sessão de caixa.
  ///
  /// Abrir, fechar e transferir são as três que definem "esta gaveta é de
  /// fulano, neste terminal". Elas ficam de fora do relay de propósito: o
  /// Caixa Principal executa o que recebe com as credenciais DELE, então uma
  /// abertura relayada seria registrada no nome do principal e do terminal
  /// dele — o oposto da regra. Um Caixa Secundário fala direto com o servidor
  /// nestas três, com o próprio operador e a própria instalação; sem servidor,
  /// ele simplesmente não abre nem fecha caixa (indisponibilidade controlada:
  /// aceitar aqui e no principal ao mesmo tempo é como duas sessões nascem).
  static bool ownsCashSession(String method, String path) =>
      method == 'POST' &&
      RegExp(
        '^/cash-register/(open|$_localId/(close|transfer))/\$',
      ).hasMatch(path);

  /// A operação abre um pedido novo.
  ///
  /// É onde o atendimento é atribuído: quem abriu o pedido é quem a cozinha
  /// vai ler como atendente na comanda.
  static bool opensOrder(String method, String path) =>
      method == 'POST' &&
      const {
        '/orders/',
        '/orders/open-command/',
        '/orders/create-with-item/',
      }.contains(path);

  /// A operação cria um recurso e precisa de um ID temporário local.
  static bool createsResource(String method, String path) =>
      method == 'POST' &&
      (path == '/customers/' ||
          path == '/orders/' ||
          path == '/orders/open-command/' ||
          // O garçom materializa o rascunho junto com o primeiro item
          // confirmado — mesmo resultado de `/orders/`, um pedido novo.
          path == '/orders/create-with-item/' ||
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
          // O app do garçom materializa o rascunho junto com o primeiro item
          // (`OrdersRepository.createOrderWithItem`); sem esta linha o
          // Caixa Principal recusava a criação com "Envelope da operação
          // local inválido" e o garçom só conseguia trabalhar em pedidos já
          // existentes.
          path == '/orders/create-with-item/' ||
          RegExp('^/orders/$id/items/\$').hasMatch(path) ||
          // Fechar, mandar para a cozinha e registrar pagamento: o resto do
          // atendimento, para que uma queda de rede não impeça a venda de
          // terminar.
          RegExp('^/orders/$id/(close|send-to-kitchen|pay)/\$').hasMatch(path) ||
          // Quantidade de um item pendente (teclas + e - do PDV). Repetir é
          // seguro: o corpo carrega a quantidade FINAL, não um incremento.
          RegExp('^/orders/$id/items/$id/quantity/\$').hasMatch(path) ||
          // Vincular/desvincular a mesa é parte de abrir o atendimento na
          // comanda — sem isso o garçom abre o pedido pelo principal e depois
          // esbarra no relay justamente na hora de dizer em que mesa o cliente
          // sentou.
          RegExp('^/commands/$id/(link-table|unlink-table)/\$').hasMatch(path) ||
          // Caixa: abrir, fechar, sangrar e suprir. O Caixa Principal aplica
          // no SQLite dele e entrega depois, com as credenciais de quem
          // originou; um secundário as encaminha para lá em vez de falar com
          // o servidor. Sem esta linha o relay recusava a operação e o
          // secundário acabava indo direto à nuvem — contornando justamente
          // quem é a autoridade da sessão.
          RegExp(
            '^/cash-register/(open|$id/(close|withdrawal|supply))/\$',
          ).hasMatch(path);
    }
    if (method == 'PATCH') {
      return path.startsWith('/customers/') ||
          // Cadastro de equipamento é configuração do PDV, não venda: um
          // Caixa Secundário tem impressora e balança próprias e precisa
          // poder corrigir porta, IP e setor sem depender do Principal. A
          // alteração é gravada aqui e entregue a ele como qualquer outra
          // operação da fila — repetir é seguro, porque um PATCH com os
          // mesmos campos leva ao mesmo cadastro.
          RegExp('^/printers/$id/\$').hasMatch(path) ||
          RegExp('^/scales/$id/\$').hasMatch(path);
    }
    if (method == 'DELETE') {
      return RegExp('^/orders/$id/items/$id/void/\$').hasMatch(path);
    }
    return false;
  }
}
