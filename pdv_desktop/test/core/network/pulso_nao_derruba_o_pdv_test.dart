import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/network/realtime_client.dart';

/// O PDV sumia da tela vinte segundos depois de abrir.
///
/// Sem diálogo, sem nada no `pdv.log` — só `app_start` e silêncio. No Visualizador
/// de Eventos do Windows aparecia `0xC000041D`,
/// `STATUS_FATAL_USER_CALLBACK_EXCEPTION`: uma exceção lançada dentro de um
/// callback que o sistema operacional invocou e ninguém pegou.
///
/// A origem era o pulso da conexão de tempo real. `socket.add` lança
/// SINCRONAMENTE quando o sink já fechou, e existe uma janela real em que isso
/// acontece: a conexão cai no nível do TCP e o `onDone` que zeraria `_socket`
/// ainda não rodou. Dentro de um `Timer.periodic` não há quem pegue — o
/// processo inteiro morre.
///
/// Vinte segundos era o intervalo do pulso. O operador via o caixa fechar
/// sozinho no meio do expediente.
class _ClienteComPulsoQueFalha extends RealtimeClient {
  _ClienteComPulsoQueFalha({
    required super.urlBuilder,
    required super.heartbeatInterval,
  });

  int tentativas = 0;

  @override
  void enviarPulso(WebSocket socket) {
    tentativas++;
    // É o que o `dart:io` faz num sink fechado.
    throw StateError('Cannot add event after closing');
  }
}

void main() {
  late HttpServer servidor;
  late List<WebSocket> conexoes;
  late String url;

  setUp(() async {
    conexoes = [];
    servidor = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    url = 'ws://127.0.0.1:${servidor.port}/ws/realtime/';
    servidor.listen((requisicao) async {
      conexoes.add(await WebSocketTransformer.upgrade(requisicao));
    });
  });

  tearDown(() async {
    for (final conexao in conexoes) {
      await conexao.close();
    }
    await servidor.close(force: true);
  });

  Future<void> esperarConectar() async {
    while (conexoes.isEmpty) {
      await Future.delayed(const Duration(milliseconds: 10));
    }
  }

  test('o pulso que falha vira RECONEXÃO, e não uma queda do processo', () async {
    final cliente = _ClienteComPulsoQueFalha(
      urlBuilder: () => url,
      heartbeatInterval: const Duration(milliseconds: 40),
    );
    final quedas = <void>[];
    cliente.onDisconnected.listen(quedas.add);

    cliente.start();
    await esperarConectar();
    // Tempo para o pulso disparar algumas vezes. Sem o tratamento, a primeira
    // exceção já teria derrubado o processo — e este teste não chegaria aqui.
    await Future.delayed(const Duration(milliseconds: 250));

    expect(cliente.tentativas, greaterThan(0), reason: 'o pulso nem chegou a sair');
    expect(quedas, isNotEmpty, reason: 'a falha do pulso precisa virar queda anunciada');

    cliente.stop();
  });

  test('e depois da falha ele volta a conectar sozinho', () async {
    final cliente = _ClienteComPulsoQueFalha(
      urlBuilder: () => url,
      heartbeatInterval: const Duration(milliseconds: 40),
    );

    cliente.start();
    await esperarConectar();
    final primeiras = conexoes.length;
    // O backoff da primeira tentativa é de 2s; esperamos um pouco mais.
    await Future.delayed(const Duration(milliseconds: 2600));

    expect(
      conexoes.length,
      greaterThan(primeiras),
      reason: 'o cliente precisa tentar de novo depois de derrubar a conexão ruim',
    );

    cliente.stop();
  });
}
