/// Fase VENDA — o caminho completo do balcao, repetido as centenas.
///
/// Abre pedido, lanca item, manda pra cozinha, cancela item, fecha e recebe.
/// Uma parte dos lancamentos vai errada de proposito: o nucleo local tem de
/// recusar com mensagem, nunca estourar excecao nem gravar lixo.
library;

import 'package:starchef_pdv/core/data/local_id.dart';

import '../chaos.dart';
import '../metrics.dart';
import '../scenario.dart';
import '../stack.dart';

class ResultadoVenda {
  ResultadoVenda(this.pedidoId, {required this.itensValidos, required this.pago});

  final String pedidoId;
  final int itensValidos;
  final bool pago;
}

Future<ResultadoVenda?> _umaVenda(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho,
  double proporcaoCaos,
) async {
  final gateway = pilha.gateway;
  final porComanda = baralho.chance(0.6);
  final corpo = porComanda
      ? {
          'restaurant': PilhaDeCarga.restauranteId,
          'order_type': 'command',
          'command': 'cmd-${baralho.inteiro(cenario.comandas.length) + 1}',
        }
      : {'restaurant': PilhaDeCarga.restauranteId, 'order_type': 'counter'};

  final criado = await medidor.medir(
    'escrita.abrir_pedido',
    () => gateway.write('POST', '/orders/', body: corpo),
    caso: porComanda ? 'comanda' : 'balcao',
  );
  if (criado == null) return null;
  final pedidoId = '${criado.payload['id']}';

  var itensValidos = 0;
  final quantidadeDeItens = 1 + baralho.inteiro(4);
  for (var indice = 0; indice < quantidadeDeItens; indice++) {
    if (baralho.chance(proporcaoCaos)) {
      final caso = baralho.escolher(
        itensInvalidos(cenario.produtosUnidade.first),
      );
      await medidor.medir(
        'escrita.lancar_item',
        () => gateway.write('POST', '/orders/$pedidoId/items/', body: caso.corpo),
        esperaFalha: true,
        caso: caso.nome,
      );
      continue;
    }
    final produto = cenario.produtosUnidade[
        baralho.inteiro(cenario.produtosUnidade.length)];
    final lancado = await medidor.medir(
      'escrita.lancar_item',
      () => gateway.write(
        'POST',
        '/orders/$pedidoId/items/',
        body: {
          'product': produto,
          'quantity': 1 + baralho.inteiro(3),
          'customer_note': baralho.observacao(),
        },
      ),
    );
    if (lancado != null) itensValidos++;
  }

  if (itensValidos == 0) return ResultadoVenda(pedidoId, itensValidos: 0, pago: false);

  if (baralho.chance(0.7)) {
    await medidor.medir(
      'escrita.enviar_cozinha',
      () => gateway.write(
        'POST',
        '/orders/$pedidoId/send-to-kitchen/',
        body: {'client_batch_serial': baralho.inteiro(999999)},
      ),
    );
  }

  // Cancelar um item ja lancado: o operador se arrepende o tempo todo.
  if (baralho.chance(0.2)) {
    final pedido = await gateway.read('/orders/$pedidoId/');
    final itens = (pedido['items'] as List?) ?? const [];
    if (itens.isNotEmpty) {
      final alvo = (itens.first as Map)['id'];
      await medidor.medir(
        'escrita.cancelar_item',
        () => gateway.write(
          'DELETE',
          '/orders/$pedidoId/items/$alvo/void/',
          body: {'reason': baralho.observacao()},
        ),
      );
    }
  }

  final fechamento = baralho.chance(proporcaoCaos)
      ? baralho.escolher(fechamentosInvalidos)
      : null;
  final fechado = await medidor.medir(
    'escrita.fechar_pedido',
    () => gateway.write(
      'POST',
      '/orders/$pedidoId/close/',
      body: fechamento?.corpo ?? {'discount': 0, 'service_fee_enabled': baralho.chance(0.5)},
    ),
    esperaFalha: fechamento != null,
    caso: fechamento?.nome ?? 'valido',
  );
  if (fechamento != null || fechado == null) {
    return ResultadoVenda(pedidoId, itensValidos: itensValidos, pago: false);
  }

  final total = '${fechado.payload['total'] ?? '0'}';
  final recebimento = baralho.chance(proporcaoCaos)
      ? baralho.escolher(recebimentosInvalidos)
      : null;
  final pago = await medidor.medir(
    'escrita.receber',
    () => gateway.write(
      'POST',
      '/orders/$pedidoId/pay/',
      body: recebimento?.corpo ??
          {
            'payment_method': baralho.escolher(cenario.formasPagamento),
            'amount': total,
          },
      context: {'cash_register': 'sessao-de-carga'},
    ),
    esperaFalha: recebimento != null,
    caso: recebimento?.nome ?? 'valido',
  );
  return ResultadoVenda(
    pedidoId,
    itensValidos: itensValidos,
    pago: recebimento == null && pago != null,
  );
}

Future<List<ResultadoVenda>> rodar(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho, {
  required int vendas,
  required double proporcaoCaos,
}) async {
  final concluidas = <ResultadoVenda>[];
  for (var indice = 0; indice < vendas; indice++) {
    final resultado =
        await _umaVenda(pilha, cenario, medidor, baralho, proporcaoCaos);
    if (resultado != null) concluidas.add(resultado);
  }

  final pagas = concluidas.where((v) => v.pago).toList();
  medidor.observar(
    '${concluidas.length} vendas abertas, ${pagas.length} pagas sem rede nenhuma',
  );

  // Todo pedido nasce com id temporario enquanto a fila nao subiu: e isso que
  // permite lancar o item seguinte sem esperar o servidor.
  final temporarios = concluidas.where((v) => LocalId.isTemporary(v.pedidoId)).length;
  medidor.verificar(
    'pedido criado offline recebe id temporario proprio',
    temporarios == concluidas.length,
    detalhe: '$temporarios de ${concluidas.length}',
  );

  // O pagamento de uma venda valida tem de estar legivel na hora, no local.
  var comPagamentoLegivel = 0;
  for (final venda in pagas.take(50)) {
    final pagamentos = await pilha.gateway.read('/orders/${venda.pedidoId}/payments/');
    final lista = (pagamentos['results'] as List?) ?? const [];
    if (lista.length == 1) comPagamentoLegivel++;
  }
  medidor.verificar(
    'venda paga mostra exatamente um recebimento no terminal',
    comPagamentoLegivel == pagas.take(50).length,
    detalhe: '$comPagamentoLegivel de ${pagas.take(50).length} conferidos',
  );
  return concluidas;
}
