/// Fase BALANCA — a Balanca Rapida do inicio ao fim, muitas vezes seguidas.
///
/// Duas coisas sao medidas juntas: a maquina de estados hands-free (que decide
/// quando o peso estabilizou, quando a comanda venceu e quando a venda pode ir)
/// e o `checkout-command` offline, que vira UMA operacao na fila — nunca uma
/// por item, senao o replay duplicaria a venda inteira.
library;

import 'package:starchef_pdv/core/hardware/scale/scale_sample.dart';
import 'package:starchef_pdv/features/scale/domain/hands_free_machine.dart';

import '../chaos.dart';
import '../metrics.dart';
import '../scenario.dart';
import '../stack.dart';

/// Uma pesagem completa na maquina de estados, do prato vazio ate a comanda.
HandsFreeState _pesarNaMaquina(
  HandsFreeMachine maquina,
  Baralho baralho,
  DateTime agora, {
  required bool lerComanda,
}) {
  maquina.start();
  final peso = baralho.peso();
  // Oscilacao antes de estabilizar: e o prato assentando na bancada.
  for (var amostra = 0; amostra < 3; amostra++) {
    maquina.onSample(
      ScaleSample(weightKg: peso + (amostra - 1) * 0.004, raw: 'sim', stable: false),
      pricePerKg: CenarioLocal.precoPorKg,
    );
  }
  maquina.onSample(
    ScaleSample(weightKg: peso, raw: 'sim', stable: true),
    pricePerKg: CenarioLocal.precoPorKg,
  );
  if (lerComanda) {
    maquina.onCommandRead('CMD${(1 + baralho.inteiro(50)).toString().padLeft(5, '0')}');
  } else {
    // Cliente abandonou o prato: o tempo tem de vencer e limpar a operacao.
    maquina.tick(agora.add(const Duration(minutes: 5)));
  }
  return maquina.state;
}

Future<void> rodar(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho, {
  required int pesagens,
  required double proporcaoCaos,
}) async {
  final maquina = HandsFreeMachine(commandTimeout: const Duration(seconds: 45));
  var concluidas = 0;
  var expiradas = 0;

  for (var indice = 0; indice < pesagens; indice++) {
    // Um abandono a cada sete pratos, por posicao e nao por sorteio: a
    // verificacao do timeout nao pode depender de a moeda cair certo num
    // perfil curto.
    final lerComanda = indice % 7 != 6;
    final relogio = Stopwatch()..start();
    final estado = _pesarNaMaquina(maquina, baralho, DateTime.now(), lerComanda: lerComanda);
    relogio.stop();
    medidor.registrar(
      Amostra(
        'balanca.ciclo_hands_free',
        relogio.elapsedMicroseconds,
        estado == HandsFreeState.creatingOrder || estado == HandsFreeState.waitingWeight
            ? vOk
            : vErroInesperado,
        caso: lerComanda ? 'comanda_lida' : 'comanda_expirada',
        detalhe: 'estado final: $estado',
      ),
    );
    if (estado == HandsFreeState.creatingOrder) {
      concluidas++;
      maquina.onOrderCreated();
      maquina.readyForNext();
    } else {
      expiradas++;
    }

    // O lancamento no pedido: offline vai com o peso bruto, porque criar uma
    // `ScaleReading` exige servidor e registrar uma leitura "de antes" seria
    // inventar um instante que nao aconteceu.
    if (!lerComanda) continue;
    final invalido = baralho.chance(proporcaoCaos);
    final corpo = invalido
        ? baralho.escolher(const [
            <String, dynamic>{'command_code': '', 'weight_kg': '1.0'},
            <String, dynamic>{'command_code': 'COMANDA-INEXISTENTE', 'weight_kg': '1.0'},
            <String, dynamic>{'command_code': 'CMD00001'},
            <String, dynamic>{'command_code': 'CMD00001', 'weight_kg': '-2'},
            <String, dynamic>{'command_code': 'CMD00001', 'weight_kg': 'meio quilo'},
          ])
        : <String, dynamic>{
            'command_code': cenario.comandas[baralho.inteiro(cenario.comandas.length)],
            'weight_kg': baralho.peso().toStringAsFixed(3),
            if (baralho.chance(0.3))
              'extras': [
                {
                  'product': cenario.produtosUnidade[baralho.inteiro(20)],
                  'quantity': 1 + baralho.inteiro(2),
                },
              ],
          };
    // `weighed_product` vem no contexto porque o preco por kg e congelado no
    // instante da estabilizacao: a tela ja sabe qual produto e por quanto, e o
    // nucleo local nao pode reconsultar o cadastro depois (uma alteracao de
    // tabela durante a pesagem mudaria o valor mostrado ao cliente).
    final contexto = <String, dynamic>{
      'weighed_product': {
        'id': cenario.produtoPorKg,
        'name': 'Buffet por quilo',
        'current_price': CenarioLocal.precoPorKg.toStringAsFixed(2),
        'pricing_unit': 'kg',
      },
    };
    await medidor.medir(
      'escrita.checkout_balanca',
      () => pilha.gateway.write(
        'POST',
        '/scales/${cenario.balanca}/checkout-command/',
        body: corpo,
        context: contexto,
      ),
      esperaFalha: invalido,
      caso: invalido ? 'pesagem_invalida' : 'valido',
    );
  }

  medidor
    ..observar('$concluidas pesagens fecharam na comanda, $expiradas expiraram no tempo')
    ..verificar(
      'pesagem sem comanda expira em vez de virar venda',
      expiradas > 0 || pesagens < 10,
      detalhe: '$expiradas expiradas em $pesagens ciclos',
    );

  // Uma pesagem offline entra como UMA operacao na fila; se entrasse item a
  // item, o replay no servidor lancaria tudo duas vezes.
  final resumo = await pilha.fila.summary(scope: PilhaDeCarga.escopo);
  medidor.observar(
    'fila apos a balanca: ${resumo.pending} pendentes, ${resumo.failed} recusadas',
  );
}
