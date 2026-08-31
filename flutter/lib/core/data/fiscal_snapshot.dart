import 'entity_catalog.dart';
import 'entity_repository.dart';

/// Monta o retrato fiscal de uma venda no instante do pagamento.
///
/// Antes, a fila fiscal guardava só `{order, cpf, client_document_id}` e toda a
/// tributação era resolvida no servidor, lendo `product.fiscal_profile` do
/// PostgreSQL. Sem servidor não havia o que emitir — a "fila offline" era, na
/// prática, uma fila de intenções que só o backend sabia executar.
///
/// O snapshot resolve isso e resolve outra coisa junto: ele é **imutável**. A
/// nota desta venda é montada com o cadastro que valia nesta venda. Se amanhã
/// alguém corrigir o NCM do produto, a nota de ontem não muda — e a de amanhã
/// sai com o valor novo, como deve ser.
///
/// O que ele NÃO faz: inventar tributação. Produto sem perfil fiscal, ou perfil
/// sem NCM, vira um registro em [FiscalSnapshot.issues] — não um `00000000`
/// silencioso que esconde cadastro incompleto até a SEFAZ recusar.
class FiscalSnapshotBuilder {
  const FiscalSnapshotBuilder({
    required this.fiscalConfigs,
    required this.fiscalProfiles,
    required this.products,
  });

  final EntityRepository fiscalConfigs;
  final EntityRepository fiscalProfiles;
  final EntityRepository products;

  /// Versão do formato. Sobe quando o conteúdo do snapshot mudar de forma que
  /// um consumidor antigo leria errado — o backend usa isso para recusar um
  /// retrato que não sabe interpretar em vez de emitir uma nota torta.
  static const version = 1;

  Future<FiscalSnapshot> build({
    required Map<String, dynamic> order,
    String? restaurantId,
    String? cpf,
    String? cpfName,
  }) async {
    final issues = <String>[];
    final config = await _resolveConfig(restaurantId);
    if (config == null) {
      issues.add('Sem configuração fiscal ativa para este restaurante.');
    }

    final profiles = await _profilesById();
    final items = <Map<String, dynamic>>[];
    var line = 0;
    var productsTotal = 0.0;
    var approxTotal = 0.0;

    for (final raw in _listOf(order, 'items')) {
      final status = '${raw['status'] ?? ''}';
      // Item cancelado ou cortesia não é faturável — mesmo recorte do servidor.
      if (status == 'cancelled' || status == 'comped') continue;
      line += 1;
      final product =
          (await products.read('${raw['product'] ?? ''}'))?.payload ??
          const <String, dynamic>{};
      final profileId = '${product['fiscal_profile'] ?? ''}';
      final profile = profiles[profileId];
      final description = '${raw['product_name'] ?? product['name'] ?? ''}';

      if (profile == null) {
        issues.add(
          profileId.isEmpty
              ? 'O produto "$description" não tem perfil fiscal.'
              : 'O perfil fiscal do produto "$description" não está neste terminal.',
        );
      } else if ('${profile['ncm'] ?? ''}'.isEmpty) {
        issues.add('O perfil fiscal "${profile['name']}" está sem NCM.');
      }

      final quantity = _number(raw['quantity']);
      final unitPrice = _number(raw['unit_price']);
      final totalPrice = _number(raw['total_price']) == 0
          ? quantity * unitPrice
          : _number(raw['total_price']);
      final taxes = _taxesOf(profile, totalPrice);
      productsTotal += totalPrice;
      approxTotal += taxes['approx_tax_value'] as double;

      items.add({
        'line_number': line,
        'product': '${raw['product'] ?? ''}',
        'code': '${product['internal_code'] ?? ''}',
        'description': description,
        'unit': '${raw['pricing_unit'] ?? product['pricing_unit'] ?? 'unit'}' == 'weight'
            ? 'KG'
            : 'UN',
        'quantity': quantity,
        'unit_price': unitPrice,
        'total_price': totalPrice,
        'fiscal_profile': profileId,
        // Carimbo da versão do cadastro usada aqui: é o que permite dizer,
        // depois, com qual regra esta nota foi montada.
        'fiscal_profile_version': '${profile?['updated_at'] ?? ''}',
        'ncm': '${profile?['ncm'] ?? ''}',
        'cest': '${profile?['cest'] ?? ''}',
        'cfop': '${profile?['cfop'] ?? ''}',
        'origem': '${profile?['origem'] ?? ''}',
        'csosn': '${profile?['csosn'] ?? ''}',
        'cst_icms': '${profile?['cst_icms'] ?? ''}',
        'pis_cst': '${profile?['pis_cst'] ?? ''}',
        'cofins_cst': '${profile?['cofins_cst'] ?? ''}',
        'icms_rate': _number(profile?['icms_rate']),
        'pis_rate': _number(profile?['pis_rate']),
        'cofins_rate': _number(profile?['cofins_rate']),
        'approx_tax_rate': _number(profile?['approx_tax_rate']),
        ...taxes,
      });
    }

    if (items.isEmpty) issues.add('O pedido não tem itens faturáveis.');

    final payments = [
      for (final payment in [
        ..._listOf(order, 'payments'),
        ..._listOf(order, 'offline_payments'),
      ])
        {
          'payment_method': '${payment['payment_method'] ?? ''}',
          'method_type': '${payment['method_type'] ?? ''}',
          'card_subtype': '${payment['card_subtype'] ?? ''}',
          'amount': _number(payment['amount']),
          'change_amount': _number(payment['change_amount']),
        },
    ];
    if (payments.isEmpty) issues.add('A venda não tem recebimento registrado.');

    return FiscalSnapshot(
      issues: issues,
      data: {
        'snapshot_version': version,
        'captured_at': DateTime.now().toUtc().toIso8601String(),
        'order': {
          'id': '${order['id'] ?? ''}',
          'sequence': order['sequence'],
          'order_type': '${order['order_type'] ?? ''}',
          'products_total': productsTotal,
          'discount': _number(order['discount']),
          'total': _number(order['total']),
          'tax_approx_total': approxTotal,
        },
        'emitter': config == null ? null : _emitterOf(config),
        'items': items,
        'payments': payments,
        'consumer': {
          'cpf': cpf ?? '',
          'name': cpfName ?? '',
        },
        'issues': issues,
      },
    );
  }

  Future<Map<String, dynamic>?> _resolveConfig(String? restaurantId) async {
    final page = await fiscalConfigs.list(
      query: {
        'page_size': 100,
        if (restaurantId != null && restaurantId.isNotEmpty)
          'restaurant': restaurantId,
      },
    );
    for (final config in page.results) {
      if (config['is_active'] == false) continue;
      return config;
    }
    return page.results.isEmpty ? null : page.results.first;
  }

  Future<Map<String, Map<String, dynamic>>> _profilesById() async {
    final page = await fiscalProfiles.list(query: {'page_size': 500});
    return {
      for (final profile in page.results) '${profile['id']}': profile,
    };
  }

  static Map<String, dynamic> _emitterOf(Map<String, dynamic> config) => {
    'fiscal_config': '${config['id'] ?? ''}',
    'fiscal_config_version': '${config['updated_at'] ?? ''}',
    'provider': '${config['provider'] ?? ''}',
    'document_model': '${config['document_model'] ?? ''}',
    'environment': '${config['environment'] ?? ''}',
    'crt': '${config['crt'] ?? ''}',
    'series': config['series'],
    'cnpj': '${config['cnpj'] ?? ''}',
    'ie': '${config['ie'] ?? ''}',
    'corporate_name': '${config['corporate_name'] ?? ''}',
    'trade_name': '${config['trade_name'] ?? ''}',
    'address_line': '${config['address_line'] ?? ''}',
    'address_number': '${config['address_number'] ?? ''}',
    'district': '${config['district'] ?? ''}',
    'city': '${config['city'] ?? ''}',
    'city_ibge': '${config['city_ibge'] ?? ''}',
    'uf': '${config['uf'] ?? ''}',
    'zip_code': '${config['zip_code'] ?? ''}',
  };

  /// Mesmo cálculo do `compute_item_taxes` do servidor. Para Simples Nacional
  /// as alíquotas costumam ser zero — o imposto já está no DAS.
  static Map<String, dynamic> _taxesOf(
    Map<String, dynamic>? profile,
    double base,
  ) {
    double pct(Object? rate) =>
        double.parse((base * _number(rate) / 100).toStringAsFixed(2));
    return {
      'icms_base': base,
      'icms_value': pct(profile?['icms_rate']),
      'pis_value': pct(profile?['pis_rate']),
      'cofins_value': pct(profile?['cofins_rate']),
      'approx_tax_value': pct(profile?['approx_tax_rate']),
    };
  }

  static List<Map<String, dynamic>> _listOf(
    Map<String, dynamic> source,
    String key,
  ) =>
      (source[key] as List? ?? const [])
          .whereType<Map>()
          .map((value) => Map<String, dynamic>.from(value))
          .toList();

  static double _number(Object? value) => switch (value) {
    num n => n.toDouble(),
    String s => double.tryParse(s.replaceAll(',', '.')) ?? 0,
    _ => 0,
  };
}

/// Retrato fiscal capturado, junto com o que ficou faltando para ele valer.
class FiscalSnapshot {
  const FiscalSnapshot({required this.data, required this.issues});

  final Map<String, dynamic> data;

  /// Cadastro incompleto encontrado na captura. Um snapshot com pendências
  /// ainda é gravado — a venda já aconteceu e o registro dela não se joga
  /// fora —, mas ele não serve para emitir sem alguém resolver a lista.
  final List<String> issues;

  bool get isComplete => issues.isEmpty;
}

/// Constrói o builder a partir do gateway, sem ele precisar conhecer os tipos.
FiscalSnapshotBuilder fiscalSnapshotBuilder(
  EntityRepository Function(String type) repository,
) => FiscalSnapshotBuilder(
  fiscalConfigs: repository(EntityCatalog.fiscalConfig),
  fiscalProfiles: repository(EntityCatalog.fiscalProfile),
  products: repository(EntityCatalog.product),
);
