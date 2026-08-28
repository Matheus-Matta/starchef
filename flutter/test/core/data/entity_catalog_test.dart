import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';

/// O catálogo é o mapa que diz "esta rota da API é este recurso local".
/// Um erro aqui não aparece como exceção: aparece como uma tela que funciona
/// online e some offline — por isso os casos-limite têm teste.
void main() {
  test('rotas mais específicas ganham das mais genéricas', () {
    // `/tables/sectors/` é prefixo-compatível com `/tables/`: sem a ordem
    // certa, um setor de mesa viraria uma mesa com id "sectors".
    expect(
      EntityCatalog.resolve('/tables/sectors/')!.type,
      EntityCatalog.tableSector,
    );
    expect(EntityCatalog.resolve('/tables/')!.type, EntityCatalog.table);
    expect(EntityCatalog.resolve('/printers/')!.type, EntityCatalog.printer);
    expect(
      EntityCatalog.resolve('/customers/addresses/')!.type,
      EntityCatalog.customerAddress,
    );
    expect(EntityCatalog.resolve('/customers/')!.type, EntityCatalog.customer);
  });

  test('separa coleção, detalhe e ação sobre o detalhe', () {
    final colecao = EntityCatalog.resolve('/orders/')!;
    expect(colecao.isCollection, isTrue);
    expect(colecao.entityId, isNull);

    final detalhe = EntityCatalog.resolve('/orders/pedido-1/')!;
    expect(detalhe.isCollection, isFalse);
    expect(detalhe.entityId, 'pedido-1');
    expect(detalhe.action, isNull);

    final acao = EntityCatalog.resolve('/orders/pedido-1/close/')!;
    expect(acao.entityId, 'pedido-1');
    expect(acao.action, 'close');

    final aninhada = EntityCatalog.resolve('/orders/p1/items/i1/void/')!;
    expect(aninhada.entityId, 'p1');
    expect(aninhada.action, 'items/i1/void');
  });

  test('ações de coleção criam um recurso, não endereçam um existente', () {
    for (final path in const [
      '/orders/open-command/',
      '/orders/create-with-item/',
      '/cash-register/open/',
      '/cash-register/current/',
    ]) {
      final route = EntityCatalog.resolve(path)!;
      expect(route.isCollection, isTrue, reason: path);
      expect(route.entityId, isNull, reason: path);
    }
  });

  test('rotas que não são recurso operacional não resolvem', () {
    for (final path in const [
      '/auth/login/',
      '/print-jobs/',
      '/reports/sales/',
    ]) {
      expect(EntityCatalog.resolve(path), isNull, reason: path);
    }
  });

  test('todo recurso que o restaurante precisa offline está no catálogo (§15)', () {
    final tipos = EntityCatalog.descriptors.map((item) => item.type).toSet();

    expect(
      tipos,
      containsAll({
        EntityCatalog.restaurant,
        EntityCatalog.product,
        EntityCatalog.category,
        EntityCatalog.addon,
        EntityCatalog.variation,
        EntityCatalog.table,
        EntityCatalog.command,
        EntityCatalog.customer,
        EntityCatalog.paymentMethod,
        EntityCatalog.cashStation,
        EntityCatalog.cashSession,
        EntityCatalog.order,
        EntityCatalog.printer,
        EntityCatalog.scale,
        EntityCatalog.fiscalConfig,
        EntityCatalog.user,
      }),
    );
  });

  test('a carga inicial vem do essencial para o acessório (§24)', () {
    final ordem = EntityCatalog.pullOrder.map((item) => item.type).toList();

    // Cardápio e configuração antes de pedidos: a tela de venda não abre sem
    // eles, e um pedido sem produto não desenha.
    expect(
      ordem.indexOf(EntityCatalog.product),
      lessThan(ordem.indexOf(EntityCatalog.order)),
    );
    expect(
      ordem.indexOf(EntityCatalog.restaurant),
      lessThan(ordem.indexOf(EntityCatalog.product)),
    );
  });

  test('modelo do WebSocket vira tipo local (§11)', () {
    expect(
      EntityCatalog.typeForRealtimeResource('menu.product'),
      EntityCatalog.product,
    );
    expect(
      EntityCatalog.typeForRealtimeResource('restaurants.command'),
      EntityCatalog.command,
    );
    expect(
      EntityCatalog.typeForRealtimeResource('printers.printer'),
      EntityCatalog.printer,
    );
    // Um recurso que o caixa não guarda localmente não vira gravação.
    expect(EntityCatalog.typeForRealtimeResource('printers.printjob'), isNull);
  });

  test('dados sigilosos são marcados para cifra em repouso (§15)', () {
    final sigilosos = EntityCatalog.descriptors
        .where((item) => item.sensitive)
        .map((item) => item.type)
        .toSet();

    // CSC, ID CSC e ambiente de emissão da NFC-e vivem aqui.
    expect(sigilosos, contains(EntityCatalog.fiscalConfig));
    expect(sigilosos, contains(EntityCatalog.user));
  });
}
