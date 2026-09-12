import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';
import 'package:starchef_pdv/core/data/fiscal_queue_service.dart';
import 'package:starchef_pdv/core/data/offline_first_gateway.dart';
import 'package:starchef_pdv/core/data/pdv_database.dart';
import 'package:starchef_pdv/core/data/sync_queue_service.dart';
import 'package:starchef_pdv/core/data/sync_service.dart';
import 'package:starchef_pdv/core/network/api_client.dart';
import 'package:starchef_pdv/core/network/offline_store.dart';
import 'package:starchef_pdv/features/home/data/pdv_repository.dart';

/// Token com claim de conta: é dele que sai o escopo do banco local.
const _token =
    'eyJhbGciOiJIUzI1NiJ9.'
    'eyJhY2NvdW50X2lkIjoiYWNjLTEifQ.'
    'assinatura-irrelevante-no-teste';

/// O cardápio inteiro tem de chegar ao balcão — não só a primeira página.
///
/// `loadCatalog` pedia `page_size: 300` e ficava com a primeira página: um
/// restaurante com 400 produtos operava com 300 e nenhum aviso. É a mesma
/// armadilha da comanda que "não existia" além da página 500.
void main() {
  late Directory directory;

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('starchef-catalogo-');
  });

  tearDown(() async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // No Windows o arquivo pode continuar preso por instantes.
    }
  });

  Future<({ApiClient api, OfflineFirstGateway gateway, PdvDatabase database})>
  build() async {
    final sep = Platform.pathSeparator;
    final database = PdvDatabase(
      file: File('${directory.path}${sep}pdv.sqlite'),
    );
    await database.ready;
    final gateway = OfflineFirstGateway(
      database: database,
      queue: SyncQueueService(database: database),
      fiscalQueue: FiscalQueueService(database: database),
    );
    final api = ApiClient(
      baseUrl: 'http://starchef.test/api/v1',
      // Nenhuma chamada pode chegar aqui: o catálogo vem do SQLite.
      client: MockClient(
        (_) async => http.Response(
          jsonEncode({'count': 0, 'results': []}),
          200,
          headers: {'content-type': 'application/json'},
        ),
      ),
      offlineStore: OfflineStore(file: File('${directory.path}${sep}legacy.sqlite')),
    );
    api.attachLocalStore(
      gateway: gateway,
      syncService: SyncService(gateway: gateway, transport: api.syncTransport),
    );
    gateway.bindSession(
      scope: '${Uri.parse('http://starchef.test/api/v1').authority}'
          '|acc-1:authenticated',
      restaurantId: 'rest-1',
    );
    return (api: api, gateway: gateway, database: database);
  }

  test('listAll segue `next` e traz um catálogo maior que uma página', () async {
    final stack = await build();
    addTearDown(() async {
      await stack.api.dispose();
      await stack.database.close();
    });
    // 750 produtos: mais que duas páginas de 300.
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      for (var i = 0; i < 750; i++)
        {
          'id': 'prod-$i',
          'name': 'Produto $i',
          'restaurant': 'rest-1',
          'current_price': '10.00',
          'pricing_unit': 'unit',
          'is_active': true,
        },
    ]);
    await stack.gateway.recordSync(EntityCatalog.product);

    final repository = PdvRepository(api: stack.api, accessToken: _token);
    final produtos = await repository.listAll(
      '/menu/products/',
      query: {'page_size': 300, 'restaurant': 'rest-1', 'is_active': true},
    );

    expect(produtos, hasLength(750));
    expect(produtos.map((p) => p['id']).toSet(), hasLength(750));
  });
}
