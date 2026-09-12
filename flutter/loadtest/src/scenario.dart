/// Semeia o SQLite local com o catalogo do restaurante.
///
/// E o equivalente ao "aquecer o cache" do runbook: sem produto, comanda e
/// forma de pagamento gravados, o PDV offline nao tem o que vender — e o teste
/// mediria a recusa, nao a operacao.
library;

import 'package:starchef_pdv/core/data/entity_catalog.dart';

import 'chaos.dart';
import 'stack.dart';

class CenarioLocal {
  CenarioLocal({
    required this.produtosUnidade,
    required this.produtoPorKg,
    required this.comandas,
    required this.mesas,
    required this.formasPagamento,
    required this.estacaoCaixa,
    required this.impressora,
    required this.balanca,
  });

  final List<String> produtosUnidade;
  final String produtoPorKg;
  final List<String> comandas;
  final List<String> mesas;
  final List<String> formasPagamento;
  final String estacaoCaixa;
  final Map<String, dynamic> impressora;
  final String balanca;

  static const precoUnidade = 12.5;
  static const precoPorKg = 59.9;
}

/// Grava o catalogo como se tivesse vindo do servidor (origem REMOTE).
///
/// Precisa ser REMOTE: dado marcado como local viraria operacao de saida e o
/// teste comecaria com a fila cheia de coisa que ninguem lancou.
Future<CenarioLocal> semear(
  PilhaDeCarga pilha, {
  required int registrosPorTipo,
  required Baralho baralho,
}) async {
  final gateway = pilha.gateway;
  const restaurante = PilhaDeCarga.restauranteId;

  final produtos = <Map<String, dynamic>>[
    for (var indice = 0; indice < registrosPorTipo; indice++)
      {
        'id': 'prod-$indice',
        'name': '${baralho.escolher(Baralho.pratos)} $indice',
        'restaurant': restaurante,
        'current_price': CenarioLocal.precoUnidade.toStringAsFixed(2),
        'pricing_unit': 'unit',
        'internal_code': 'LT$indice',
        'is_active': true,
      },
    {
      'id': 'prod-kg',
      'name': 'Buffet por quilo',
      'restaurant': restaurante,
      'current_price': CenarioLocal.precoPorKg.toStringAsFixed(2),
      'pricing_unit': 'kg',
      'is_active': true,
    },
  ];
  await gateway.repository(EntityCatalog.product).applyRemoteList(produtos);
  await gateway.recordSync(EntityCatalog.product);

  final comandas = <Map<String, dynamic>>[
    for (var indice = 1; indice <= registrosPorTipo ~/ 4 + 20; indice++)
      {
        'id': 'cmd-$indice',
        'number': indice,
        'code': 'CMD${indice.toString().padLeft(5, '0')}',
        'status': 'free',
        'restaurant': restaurante,
        'is_active': true,
      },
  ];
  await gateway.repository(EntityCatalog.command).applyRemoteList(comandas);
  await gateway.recordSync(EntityCatalog.command);

  final mesas = <Map<String, dynamic>>[
    for (var indice = 1; indice <= registrosPorTipo ~/ 10 + 10; indice++)
      {
        'id': 'mesa-$indice',
        'number': indice,
        'restaurant': restaurante,
        'status': 'free',
        'is_active': true,
      },
  ];
  await gateway.repository(EntityCatalog.table).applyRemoteList(mesas);
  await gateway.recordSync(EntityCatalog.table);

  const formas = [
    {'id': 'dinheiro', 'name': 'Dinheiro', 'method_type': 'cash', 'restaurant': restaurante},
    {'id': 'cartao', 'name': 'Cartao', 'method_type': 'card', 'restaurant': restaurante},
    {'id': 'pix', 'name': 'PIX', 'method_type': 'pix', 'restaurant': restaurante},
  ];
  await gateway.repository(EntityCatalog.paymentMethod).applyRemoteList(
    List<Map<String, dynamic>>.from(formas),
  );
  await gateway.recordSync(EntityCatalog.paymentMethod);

  await gateway.repository(EntityCatalog.cashStation).applyRemoteList([
    {'id': 'caixa-1', 'name': 'Caixa 1', 'restaurant': restaurante},
  ]);
  await gateway.recordSync(EntityCatalog.cashStation);

  const impressora = <String, dynamic>{
    'id': 'impressora-1',
    'name': 'Cozinha',
    'restaurant': restaurante,
    'connection_type': 'network',
    'driver_type': 'escpos',
    'endpoint': '127.0.0.1',
    'is_active': true,
  };
  await gateway.repository(EntityCatalog.printer).applyRemoteList([impressora]);
  await gateway.recordSync(EntityCatalog.printer);

  await gateway.repository(EntityCatalog.scale).applyRemoteList([
    {
      'id': 'balanca-1',
      'name': 'Balanca do buffet',
      'restaurant': restaurante,
      'protocol': 'generic',
      'port': 'COM9',
      'product': 'prod-kg',
      'printer': 'impressora-1',
      'is_active': true,
    },
  ]);
  await gateway.recordSync(EntityCatalog.scale);

  return CenarioLocal(
    produtosUnidade: [for (var i = 0; i < registrosPorTipo; i++) 'prod-$i'],
    produtoPorKg: 'prod-kg',
    comandas: [for (final comanda in comandas) '${comanda['code']}'],
    mesas: [for (final mesa in mesas) '${mesa['id']}'],
    formasPagamento: const ['dinheiro', 'cartao', 'pix'],
    estacaoCaixa: 'caixa-1',
    impressora: impressora,
    balanca: 'balanca-1',
  );
}
