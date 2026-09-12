/// Fase CAIXA — o turno inteiro da gaveta, sem rede.
///
/// Abertura, sangria, suprimento e fechamento sao as operacoes que o PDV
/// passou a fazer offline (§ "O que ainda exige servidor"). Se alguma delas
/// travar ou aceitar valor absurdo, o operador fecha o dia com diferenca.
library;

import '../chaos.dart';
import '../metrics.dart';
import '../scenario.dart';
import '../stack.dart';

Future<String?> rodar(
  PilhaDeCarga pilha,
  CenarioLocal cenario,
  Medidor medidor,
  Baralho baralho, {
  required int movimentos,
  required double proporcaoCaos,
}) async {
  final gateway = pilha.gateway;

  // Abertura errada primeiro: o caixa nao pode abrir sem estacao valida nem
  // com valor de abertura ilegivel.
  for (final caso in caixaInvalido.where((c) => c.nome.startsWith('abertura'))) {
    await medidor.medir(
      'escrita.abrir_caixa',
      () => gateway.write('POST', '/cash-register/open/', body: caso.corpo),
      esperaFalha: true,
      caso: caso.nome,
    );
  }

  // Se alguma dessas aberturas invalidas passou, ela deixou uma sessao aberta
  // e a proxima abertura legitima seria recusada por conflito. Fecha aqui para
  // a fase seguir; o defeito ja ficou registrado como `lixo_aceito`.
  final residual = await gateway.read('/cash-register/current/', query: {
    'restaurant': PilhaDeCarga.restauranteId,
  });
  if (residual['_empty'] != true && residual['id'] != null) {
    medidor.observar(
      'uma abertura de caixa INVALIDA criou a sessao ${residual['id']} '
      '(estacao=${residual['cash_station']}, abertura=${residual['opening_amount']}) — '
      'ela foi fechada para a fase continuar',
    );
    await gateway.write(
      'POST',
      '/cash-register/${residual['id']}/close/',
      body: const {'actual_amount': '0.00', 'notes': 'limpeza do teste de carga'},
    );
  }

  final aberto = await medidor.medir(
    'escrita.abrir_caixa',
    () => gateway.write(
      'POST',
      '/cash-register/open/',
      body: {
        'cash_station': cenario.estacaoCaixa,
        'opening_amount': '150.00',
        'station': pilha.nome,
      },
    ),
  );
  if (aberto == null) {
    medidor.verificar('caixa abre sem rede', false, detalhe: 'a abertura falhou');
    return null;
  }
  final sessao = '${aberto.payload['id']}';

  final atual = await medidor.medir(
    'leitura.caixa_atual',
    () => gateway.read('/cash-register/current/', query: {
      'restaurant': PilhaDeCarga.restauranteId,
    }),
  );
  medidor.verificar(
    'sessao aberta e encontrada por /cash-register/current/',
    atual != null && atual['_empty'] != true,
    detalhe: 'id=${atual?['id']}',
  );

  for (var indice = 0; indice < movimentos; indice++) {
    final tipo = baralho.chance(0.5) ? 'withdrawal' : 'supply';
    if (baralho.chance(proporcaoCaos)) {
      final caso = baralho.escolher(
        caixaInvalido.where((c) => c.nome.startsWith('sangria')).toList(),
      );
      await medidor.medir(
        'escrita.movimento_caixa',
        () => gateway.write(
          'POST',
          '/cash-register/$sessao/$tipo/',
          body: caso.corpo,
        ),
        esperaFalha: true,
        caso: caso.nome,
      );
      continue;
    }
    await medidor.medir(
      'escrita.movimento_caixa',
      () => gateway.write(
        'POST',
        '/cash-register/$sessao/$tipo/',
        body: {
          'amount': (5 + baralho.inteiro(120)).toStringAsFixed(2),
          'reason': baralho.observacao(),
          if (tipo == 'withdrawal') 'destination': 'cofre' else 'source': 'gerente',
        },
      ),
      caso: tipo,
    );
  }

  await medidor.medir(
    'escrita.fechar_caixa',
    () => gateway.write(
      'POST',
      '/cash-register/$sessao/close/',
      body: const {'notes': 'sem valor conferido'},
    ),
    esperaFalha: true,
    caso: 'fechamento_sem_valor',
  );

  final fechado = await medidor.medir(
    'escrita.fechar_caixa',
    () => gateway.write(
      'POST',
      '/cash-register/$sessao/close/',
      body: {'actual_amount': '742.50', 'notes': 'conferido'},
    ),
  );
  medidor.verificar(
    'caixa fecha sem rede e devolve a sessao encerrada',
    fechado != null,
    detalhe: 'status=${fechado?.payload['status']}',
  );

  // Depois de fechar, `current` nao pode mais devolver a sessao: aceitar isso
  // autorizaria sangria numa gaveta que ja foi conferida.
  final depois = await gateway.read('/cash-register/current/', query: {
    'restaurant': PilhaDeCarga.restauranteId,
  });
  medidor.verificar(
    'caixa fechado some de /cash-register/current/',
    depois['_empty'] == true || depois['id'] != sessao,
    detalhe: 'resposta=${depois['id'] ?? depois['detail']}',
  );
  return sessao;
}
