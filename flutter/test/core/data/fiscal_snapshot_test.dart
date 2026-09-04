import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/data/entity_catalog.dart';

import 'pdv_test_support.dart';

/// O retrato fiscal da venda é capturado no terminal, no instante do
/// pagamento (§16).
///
/// Antes a fila fiscal guardava `{order, cpf}` e a tributação inteira era
/// resolvida no servidor. A fila era "offline" só no nome: sem backend não
/// havia o que emitir. Aqui se garante que o que fica gravado basta para
/// montar a NFC-e — e que cadastro incompleto aparece como pendência em vez de
/// virar um NCM zerado que a SEFAZ recusa depois.
void main() {
  late TestPdvStack stack;

  setUp(() async {
    stack = await TestPdvStack.create();
    await stack.gateway.repository(EntityCatalog.fiscalConfig).applyRemoteList([
      {
        'id': 'config-1',
        'restaurant': 'rest-1',
        'is_active': true,
        'provider': 'focus_nfe',
        'document_model': '65',
        'environment': '2',
        'crt': '1',
        'series': 1,
        'cnpj': '11222333000181',
        'corporate_name': 'Loja Teste LTDA',
        'uf': 'SP',
        'city': 'São Paulo',
        'city_ibge': '3550308',
        'updated_at': '2026-08-01T10:00:00Z',
      },
    ]);
    await stack.gateway
        .repository(EntityCatalog.fiscalProfile)
        .applyRemoteList([
          {
            'id': 'perfil-1',
            'name': 'Salgados',
            'ncm': '19059090',
            'cfop': '5102',
            'csosn': '102',
            'origem': '0',
            'pis_cst': '49',
            'cofins_cst': '49',
            'icms_rate': '0',
            'approx_tax_rate': '12.00',
            'updated_at': '2026-08-02T10:00:00Z',
          },
        ]);
    await stack.gateway.repository(EntityCatalog.product).applyRemoteList([
      {
        'id': 'prod-1',
        'name': 'Pastel de queijo',
        'restaurant': 'rest-1',
        'internal_code': 'PAS01',
        'current_price': '7.50',
        'pricing_unit': 'unit',
        'fiscal_profile': 'perfil-1',
      },
      {
        'id': 'prod-2',
        'name': 'Refrigerante',
        'restaurant': 'rest-1',
        'internal_code': 'REF01',
        'current_price': '5.00',
        'pricing_unit': 'unit',
      },
    ]);
  });

  tearDown(() async => stack.dispose());

  Future<String> soldOrder({String product = 'prod-1'}) async {
    final created = await stack.gateway.write(
      'POST',
      '/orders/',
      body: {'restaurant': 'rest-1', 'order_type': 'counter'},
    );
    final orderId = '${created.payload['id']}';
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/items/',
      body: {'product': product, 'quantity': 2},
    );
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/close/',
      body: {'discount': 0},
    );
    await stack.gateway.write(
      'POST',
      '/orders/$orderId/pay/',
      body: {'payment_method': 'dinheiro', 'amount': '15.00'},
      context: {
        'payment_method': {'id': 'dinheiro', 'method_type': 'cash'},
      },
    );
    return orderId;
  }

  test('o retrato guarda emitente, itens tributados e pagamentos', () async {
    final orderId = await soldOrder();

    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': orderId, 'cpf': '12345678909'},
    );

    final snapshot = (await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    )).single.snapshot!;

    expect(snapshot['snapshot_version'], 1);
    final emitter = snapshot['emitter'] as Map<String, dynamic>;
    expect(emitter['cnpj'], '11222333000181');
    expect(emitter['document_model'], '65');
    // Carimbo do cadastro usado: é o que permite dizer, depois, com qual
    // versão da regra esta nota foi montada.
    expect(emitter['fiscal_config_version'], '2026-08-01T10:00:00Z');

    final items = (snapshot['items'] as List).cast<Map<String, dynamic>>();
    expect(items, hasLength(1));
    expect(items.single['ncm'], '19059090');
    expect(items.single['cfop'], '5102');
    expect(items.single['csosn'], '102');
    expect(items.single['code'], 'PAS01');
    expect(items.single['quantity'], 2);
    expect(items.single['total_price'], 15.0);
    // Tributos aproximados (Lei 12.741): 12% de 15,00.
    expect(items.single['approx_tax_value'], 1.8);
    expect(items.single['fiscal_profile_version'], '2026-08-02T10:00:00Z');

    final payments = (snapshot['payments'] as List).cast<Map<String, dynamic>>();
    expect(payments.single['method_type'], 'cash');
    expect(payments.single['amount'], 15.0);

    expect((snapshot['consumer'] as Map)['cpf'], '12345678909');
    expect(snapshot['issues'], isEmpty);
  });

  test('produto sem perfil fiscal vira pendência, não NCM inventado', () async {
    final orderId = await soldOrder(product: 'prod-2');

    final result = await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': orderId},
    );

    final document = (await stack.fiscalQueue.documents(
      scope: TestPdvStack.scope,
    )).single;
    final items = (document.snapshot!['items'] as List)
        .cast<Map<String, dynamic>>();
    // Sem perfil, o campo fica VAZIO. Um "00000000" aqui esconderia o
    // cadastro incompleto até a SEFAZ recusar a nota.
    expect(items.single['ncm'], '');
    expect(items.single['cfop'], '');
    expect(
      document.snapshot!['issues'],
      contains(contains('não tem perfil fiscal')),
    );
    // E a tela recebe a lista para avisar quem está no balcão.
    expect(result.payload['_fiscal_issues'], isNotEmpty);
  });

  test('o retrato é imutável: mudar o cadastro depois não mexe na nota', () async {
    final orderId = await soldOrder();
    await stack.gateway.write(
      'POST',
      '/invoices/emit/',
      body: {'order': orderId},
    );

    await stack.gateway
        .repository(EntityCatalog.fiscalProfile)
        .applyRemote({
          'id': 'perfil-1',
          'name': 'Salgados',
          'ncm': '21069090',
          'cfop': '5405',
          'updated_at': '2026-09-01T10:00:00Z',
        });

    final items =
        ((await stack.fiscalQueue.documents(
          scope: TestPdvStack.scope,
        )).single.snapshot!['items'] as List).cast<Map<String, dynamic>>();

    expect(items.single['ncm'], '19059090');
    expect(items.single['cfop'], '5102');
  });
}
