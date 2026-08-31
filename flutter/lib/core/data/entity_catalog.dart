/// Catálogo dos recursos que o restaurante precisa ter no SQLite (§15).
///
/// Cada descritor diz três coisas: **qual rota da API** representa o recurso,
/// **qual tipo de entidade** ele vira localmente e **como o registro é
/// indexado** para consulta offline (restaurante, pai, situação).
///
/// Um único catálogo evita a duplicação que existia antes — a lista de rotas
/// cacheáveis estava no `ApiClient`, a lista de rotas relayáveis no
/// `LocalTopologyService` e a lista de rotas carregadas na abertura no
/// `PdvRepository`. As três divergiram ao longo do tempo, e o sintoma era um
/// recurso que funcionava online e sumia offline.
library;

import 'local_id.dart';

enum EntityOrdering {
  /// Mais recente primeiro: pedidos, movimentações, sessões de caixa.
  recentFirst,

  /// Alfabética por nome: cardápio, mesas, impressoras, formas de pagamento.
  byName,
}

class EntityDescriptor {
  const EntityDescriptor({
    required this.type,
    required this.collectionPath,
    this.restaurantField = 'restaurant',
    this.parentField,
    this.statusField,
    this.singleton = false,
    this.pullOnStartup = true,
    this.pullPriority = 50,
    this.sensitive = false,
    this.ordering = EntityOrdering.byName,
    this.sharedWithSecondary = true,
    this.codeFields = const [],
  });

  /// Nome do tipo dentro da tabela `entities`.
  final String type;

  /// Rota de coleção na API (`/menu/products/`).
  final String collectionPath;

  /// Campo do payload que identifica o restaurante dono do registro.
  final String? restaurantField;

  /// Campo do payload que aponta para a entidade-pai (item -> pedido).
  final String? parentField;

  /// Campo do payload usado como situação (`status`, `state`).
  final String? statusField;

  /// Campos que um leitor de código pode ler, em ORDEM DE PRIORIDADE.
  ///
  /// No produto, `ean` vem antes de `internal_code`: o código de barras é o
  /// que está impresso na embalagem, e o código interno é a etiqueta da casa.
  /// Um mesmo número pode existir nos dois papéis em produtos diferentes, e
  /// nesse caso quem ganha é o que o leitor de fato leu.
  final List<String> codeFields;

  /// Recurso de instância única (a sessão de caixa aberta, por exemplo).
  final bool singleton;

  /// Entra na carga inicial e no delta sync periódico (§14).
  final bool pullOnStartup;

  /// Menor valor sincroniza primeiro. Cardápio e configuração vêm antes de
  /// pedidos porque a tela de venda não abre sem eles.
  final int pullPriority;

  /// Guarda credencial ou dado fiscal sigiloso (§15): o payload é cifrado em
  /// repouso antes de tocar o disco.
  final bool sensitive;

  /// Ordenação padrão da listagem local, gravada em `sort_key` para que a
  /// paginação SQL (§13) devolva a mesma ordem que a API devolveria.
  final EntityOrdering ordering;

  /// O Caixa Principal entrega este recurso a um secundário ou aplicativo?
  ///
  /// `false` para o que não pertence a quem só atende: a credencial fiscal da
  /// loja e o cadastro de usuários. Um tablet de garçom perdido no salão não
  /// pode carregar o CSC da NFC-e nem a lista de senhas.
  final bool sharedWithSecondary;

  /// Rota de detalhe de um registro (`/menu/products/<id>/`).
  String detailPath(String id) => '$collectionPath$id/';
}

/// Como uma rota da API foi resolvida contra o catálogo.
class EntityRoute {
  const EntityRoute({
    required this.descriptor,
    required this.isCollection,
    this.entityId,
    this.action,
  });

  final EntityDescriptor descriptor;

  /// `true` para `/menu/products/`, `false` para `/menu/products/<id>/`.
  final bool isCollection;

  /// Identificador presente na rota de detalhe.
  final String? entityId;

  /// Sufixo de ação sobre o detalhe (`close`, `pay`, `items`).
  final String? action;

  String get type => descriptor.type;
}

abstract final class EntityCatalog {
  /// Tipos referenciados por nome no resto do código, sem literais soltos.
  static const restaurant = 'restaurant';
  static const branch = 'branch';
  static const product = 'product';
  static const category = 'category';
  static const addon = 'addon';
  static const variation = 'variation';
  static const table = 'table';
  static const tableSector = 'table_sector';
  static const command = 'command';
  static const customer = 'customer';
  static const customerAddress = 'customer_address';
  static const paymentMethod = 'payment_method';
  static const cashStation = 'cash_station';
  static const cashSession = 'cash_session';
  static const printer = 'printer';
  static const scale = 'scale';
  static const order = 'order';
  static const user = 'user';
  static const role = 'role';
  static const fiscalConfig = 'fiscal_config';
  static const fiscalProfile = 'fiscal_profile';

  /// Ordem importa: rotas mais específicas primeiro, porque `/tables/sectors/`
  /// é prefixo-compatível com `/tables/` e resolveria para o recurso errado.
  static const List<EntityDescriptor> descriptors = [
    // --- Estabelecimento e configuração (§15 Restaurante / Fiscal) ---------
    EntityDescriptor(
      type: restaurant,
      collectionPath: '/restaurants/',
      restaurantField: null,
      pullPriority: 0,
    ),
    EntityDescriptor(
      type: branch,
      collectionPath: '/branches/',
      pullPriority: 1,
      sharedWithSecondary: false,
    ),
    EntityDescriptor(
      type: fiscalConfig,
      collectionPath: '/fiscal/config/',
      pullPriority: 2,
      sensitive: true,
      sharedWithSecondary: false,
    ),
    EntityDescriptor(
      type: fiscalProfile,
      collectionPath: '/fiscal/profiles/',
      // Cadastro da CONTA, não de um restaurante (como perfis de acesso e
      // usuários): filtrar o pull por restaurante deixaria de fora justamente
      // os perfis compartilhados, que são todos eles.
      restaurantField: null,
      pullPriority: 3,
      sharedWithSecondary: false,
    ),

    // --- Cardápio (§15 Produtos) -----------------------------------------
    EntityDescriptor(
      type: category,
      collectionPath: '/menu/categories/',
      pullPriority: 10,
    ),
    EntityDescriptor(
      type: product,
      collectionPath: '/menu/products/',
      statusField: 'is_active',
      pullPriority: 11,
      codeFields: ['ean', 'internal_code'],
    ),
    EntityDescriptor(
      type: addon,
      collectionPath: '/menu/addons/',
      parentField: 'product',
      pullPriority: 12,
    ),
    EntityDescriptor(
      type: variation,
      collectionPath: '/menu/variations/',
      parentField: 'product',
      pullPriority: 13,
    ),

    // --- Salão -----------------------------------------------------------
    EntityDescriptor(
      type: tableSector,
      collectionPath: '/tables/sectors/',
      pullPriority: 20,
    ),
    EntityDescriptor(
      type: table,
      collectionPath: '/tables/',
      statusField: 'status',
      pullPriority: 21,
    ),
    EntityDescriptor(
      type: command,
      collectionPath: '/commands/',
      statusField: 'status',
      pullPriority: 22,
      // A comanda é lida pelo código impresso nela e, quando o operador
      // digita, pelo número.
      codeFields: ['code', 'number'],
    ),

    // --- Clientes e recebimento ------------------------------------------
    EntityDescriptor(
      type: customerAddress,
      collectionPath: '/customers/addresses/',
      parentField: 'customer',
      pullOnStartup: false,
      pullPriority: 29,
    ),
    EntityDescriptor(
      type: customer,
      collectionPath: '/customers/',
      pullPriority: 30,
    ),
    EntityDescriptor(
      type: paymentMethod,
      collectionPath: '/payments/methods/',
      pullPriority: 31,
    ),

    // --- Caixa (§15 Caixa) ------------------------------------------------
    EntityDescriptor(
      type: cashStation,
      collectionPath: '/cash-stations/',
      pullPriority: 32,
    ),
    EntityDescriptor(
      type: cashSession,
      collectionPath: '/cash-register/',
      // O caixa cadastrado é o "pai" da sessão. Gravar isso em `parent_id`
      // permite que a exclusividade ("uma sessão não finalizada por caixa")
      // seja resolvida em SQL, dentro da mesma transação que grava a abertura.
      parentField: 'cash_station',
      statusField: 'status',
      pullPriority: 33,
      ordering: EntityOrdering.recentFirst,
    ),

    // --- Periféricos (§18, §19): a CONFIGURAÇÃO fica local; a execução
    // continua no terminal que alcança o equipamento fisicamente.
    EntityDescriptor(
      type: printer,
      collectionPath: '/printers/',
      pullPriority: 41,
    ),
    EntityDescriptor(
      type: scale,
      collectionPath: '/scales/',
      pullPriority: 42,
    ),

    // --- Usuários e permissões (§15 Usuários) -----------------------------
    EntityDescriptor(
      type: role,
      collectionPath: '/roles/',
      restaurantField: null,
      pullPriority: 50,
      sharedWithSecondary: false,
    ),
    EntityDescriptor(
      type: user,
      collectionPath: '/users/',
      restaurantField: null,
      pullPriority: 51,
      sensitive: true,
      sharedWithSecondary: false,
    ),

    // --- Operação --------------------------------------------------------
    EntityDescriptor(
      type: order,
      collectionPath: '/orders/',
      statusField: 'status',
      pullPriority: 60,
      ordering: EntityOrdering.recentFirst,
    ),
  ];

  static final Map<String, EntityDescriptor> _byType = {
    for (final descriptor in descriptors) descriptor.type: descriptor,
  };

  static EntityDescriptor? byType(String type) => _byType[type];

  /// Descritores na ordem em que devem ser baixados na carga inicial.
  static List<EntityDescriptor> get pullOrder =>
      descriptors.where((item) => item.pullOnStartup).toList()
        ..sort((a, b) => a.pullPriority.compareTo(b.pullPriority));

  /// Ações sobre um recurso que o armazenamento local sabe aplicar sozinho.
  ///
  /// A lista é fechada de propósito. Uma ação desconhecida caindo no caminho
  /// genérico de escrita seria interpretada como uma alteração no PRÓPRIO
  /// recurso — `DELETE /orders/<id>/payments/<id>/` chegou a excluir o pedido
  /// inteiro em vez de estornar um recebimento.
  static const localActions = <String, Set<String>>{
    order: {'items', 'close', 'pay', 'send-to-kitchen', 'quantity'},
    cashSession: {'open', 'close', 'withdrawal', 'supply', 'approve'},
    command: {'link-table', 'unlink-table'},
  };

  /// A ação desta rota pode ser aplicada localmente?
  ///
  /// `null` (uma escrita direta no recurso) sempre pode; o resto precisa estar
  /// na lista. Cancelamento de item e remoção de um recebimento ainda na fila
  /// são as ações aninhadas aceitas.
  static bool isLocalAction(String type, String? action) {
    if (action == null || action.isEmpty) return true;
    if (type == order &&
        RegExp(r'^items/[^/]+/void$').hasMatch(action)) {
      return true;
    }
    if (type == order && isPendingPaymentAction(action)) return true;
    return localActions[type]?.contains(action) ?? false;
  }

  /// `payments/<id>` de um recebimento que ainda não subiu.
  ///
  /// Um pagamento lançado aqui só existe neste terminal até a fila entregá-lo,
  /// e o identificador dele é temporário. Mandar esse `offline-…` para a API
  /// devolvia "não é um UUID válido" e travava o operador: para desfazer o
  /// lançamento não há nada a cancelar no servidor — o cancelamento é local.
  /// Com o id definitivo a rota volta a ser do servidor, que é quem sabe
  /// reabrir mesa, comanda e estorno de estoque.
  static bool isPendingPaymentAction(String action) {
    final match = RegExp(r'^payments/([^/]+)$').firstMatch(action);
    return match != null && LocalId.isTemporary(match.group(1));
  }

  /// Modelo do backend (`app_label.modelname`) -> tipo local.
  ///
  /// O WebSocket avisa "mudou `menu.product` id X"; sem esta tradução o
  /// evento não teria como virar uma gravação no SQLite e continuaria sendo
  /// só uma dica para a tela reler da rede (§11).
  static const realtimeResources = <String, String>{
    'restaurants.restaurant': restaurant,
    'restaurants.branch': branch,
    'restaurants.table': table,
    'restaurants.tablesector': tableSector,
    'restaurants.command': command,
    'menu.product': product,
    'menu.productcategory': category,
    'menu.productaddon': addon,
    'menu.productvariation': variation,
    'customers.customer': customer,
    'payments.paymentmethod': paymentMethod,
    'payments.cashstation': cashStation,
    'payments.cashregister': cashSession,
    'orders.order': order,
    'printers.printer': printer,
    'printers.scale': scale,
    'invoices.fiscalconfig': fiscalConfig,
    'invoices.fiscalprofile': fiscalProfile,
    'accounts.user': user,
    'accounts.role': role,
  };

  /// Tipo local correspondente a um recurso do WebSocket, se houver.
  static String? typeForRealtimeResource(String resource) =>
      realtimeResources[resource];

  /// Resolve uma rota da API para um descritor.
  ///
  /// Devolve `null` quando a rota não representa uma entidade operacional —
  /// login, trabalho de impressão, leitura de balança e emissão fiscal
  /// continuam com o tratamento que já tinham.
  static EntityRoute? resolve(String path) {
    final clean = path.split('?').first;
    for (final descriptor in descriptors) {
      if (!clean.startsWith(descriptor.collectionPath)) continue;
      final rest = clean
          .substring(descriptor.collectionPath.length)
          .split('/')
          .where((segment) => segment.isNotEmpty)
          .toList();
      if (rest.isEmpty) {
        return EntityRoute(descriptor: descriptor, isCollection: true);
      }
      // `/orders/open-command/` e `/orders/create-with-item/` são ações de
      // coleção: criam um pedido, não endereçam um existente.
      if (rest.length == 1 && _collectionActions.contains(rest.first)) {
        return EntityRoute(
          descriptor: descriptor,
          isCollection: true,
          action: rest.first,
        );
      }
      return EntityRoute(
        descriptor: descriptor,
        isCollection: false,
        entityId: rest.first,
        action: rest.length > 1 ? rest.sublist(1).join('/') : null,
      );
    }
    return null;
  }

  static const _collectionActions = {
    'open-command',
    'create-with-item',
    'current',
    'open',
    'close',
  };
}
