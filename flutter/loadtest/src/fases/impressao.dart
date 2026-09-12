/// Fase IMPRESSAO — a fila local de cupons sob rajada.
///
/// Duas perguntas: o cupom e montado rapido o bastante para o cliente nao
/// esperar na frente do caixa, e a fila aguenta a impressora falhando sem
/// perder trabalho nem imprimir duas vezes.
library;

import 'package:starchef_pdv/features/devices/domain/local_print_renderer.dart';

import '../chaos.dart';
import '../metrics.dart';
import '../scenario.dart';
import '../stack.dart';

Map<String, dynamic> _pedidoDeExemplo(Baralho baralho, int indice) => {
  'id': 'pedido-$indice',
  'sequence': indice,
  'status': 'paid',
  'subtotal': '87.40',
  'service_fee': '8.74',
  'discount': '0.00',
  'total': '96.14',
  'created_at': DateTime.now().toUtc().toIso8601String(),
  'items': [
    for (var item = 0; item < 3 + baralho.inteiro(6); item++)
      {
        'id': 'item-$indice-$item',
        'product_name': baralho.escolher(Baralho.pratos),
        'quantity': '${1 + baralho.inteiro(3)}',
        'unit_price': '12.50',
        'total': '25.00',
        'status': 'sent',
        'customer_note': baralho.observacao(),
      },
  ],
};

Future<void> rodar(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho, {
  required int cupons,
}) async {
  const restaurante = <String, dynamic>{
    'id': PilhaDeCarga.restauranteId,
    'trade_name': 'Restaurante de Carga',
    'legal_name': 'Carga LTDA',
    'cnpj': '00.000.000/0001-00',
  };

  for (var indice = 0; indice < cupons; indice++) {
    final pedido = _pedidoDeExemplo(baralho, indice);

    // Renderizacao: e o custo que aparece entre apertar "imprimir" e o papel
    // comecar a sair. Um cupom nao pode levar mais que alguns milissegundos.
    final relogio = Stopwatch()..start();
    final conteudo = LocalPrintRenderer.customerReceipt(
      order: pedido,
      restaurant: restaurante,
      payments: const [
        {'method_name': 'Dinheiro', 'amount': '100.00'},
      ],
      operatorName: baralho.pessoa(),
    );
    relogio.stop();
    medidor.registrar(
      Amostra(
        'render.cupom',
        relogio.elapsedMicroseconds,
        conteudo.isEmpty ? vErroInesperado : vOk,
        detalhe: conteudo.isEmpty ? 'cupom vazio' : '',
      ),
    );

    await medidor.medir(
      'impressao.enfileirar',
      () => pilha.filaImpressao.enqueue(
        scope: PilhaDeCarga.escopo,
        printer: cenario.impressora,
        jobType: 'receipt',
        content: conteudo,
      ),
    );
  }

  // A impressora falha e a fila tem de segurar o trabalho, nao perde-lo.
  var reservados = 0;
  var devolvidos = 0;
  for (var tentativa = 0; tentativa < cupons ~/ 4 + 1; tentativa++) {
    final entrada = await medidor.medir(
      'impressao.reservar',
      () => pilha.filaImpressao.claimNext(scope: PilhaDeCarga.escopo),
    );
    if (entrada == null) break;
    reservados++;
    if (baralho.chance(0.35)) {
      await pilha.filaImpressao.markRetry(
        entrada.id,
        attempts: entrada.attempts + 1,
        error: 'impressora sem papel (simulado)',
      );
      devolvidos++;
    } else {
      await pilha.filaImpressao.markPrinted(entrada.id);
    }
  }

  final resumo = await pilha.filaImpressao.summary(scope: PilhaDeCarga.escopo);
  medidor
    ..observar(
      '$cupons cupons enfileirados, $reservados reservados, $devolvidos devolvidos por falha',
    )
    ..verificar(
      'cupom que falhou volta para a fila em vez de sumir',
      devolvidos == 0 || resumo.pending > 0,
      detalhe: '${resumo.pending} pendentes, ${resumo.failed} recusados',
    )
    ..verificar(
      'nenhum cupom ficou reservado sem dono depois do ciclo',
      resumo.pending + resumo.failed <= cupons,
      detalhe: 'fila com ${resumo.total} de $cupons enfileirados',
    );
}
