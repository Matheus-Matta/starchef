import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/realtime_client.dart';

void main() {
  late HttpServer server;
  late List<WebSocket> serverSockets;
  late List<String?> authorizationHeaders;
  late String url;

  setUp(() async {
    serverSockets = [];
    authorizationHeaders = [];
    server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    url = 'ws://127.0.0.1:${server.port}/ws/realtime/';
    server.listen((request) async {
      authorizationHeaders.add(request.headers.value('authorization'));
      serverSockets.add(await WebSocketTransformer.upgrade(request));
    });
  });

  tearDown(() async {
    for (final socket in serverSockets) {
      await socket.close();
    }
    await server.close(force: true);
  });

  Future<void> waitForServerSocket() async {
    while (serverSockets.isEmpty) {
      await Future.delayed(const Duration(milliseconds: 10));
    }
  }

  test('entrega eventos do servidor e ignora mensagens de controle', () async {
    final client = RealtimeClient(urlBuilder: () => url);
    addTearDown(client.dispose);
    final firstEvent = client.events.first;

    client.start();
    await client.onConnected.first.timeout(const Duration(seconds: 5));
    await waitForServerSocket();

    // Mensagens de controle não são "algo mudou": não devem chegar como
    // evento de dados, senão todo reconecta viraria um falso positivo.
    serverSockets.single.add(jsonEncode({'event': 'connected', 'payload': {}}));
    serverSockets.single.add(jsonEncode({'event': 'pong', 'payload': {}}));
    serverSockets.single.add(
      jsonEncode({
        'event': 'model.updated',
        'payload': {
          'resource': 'printers.printjob',
          'id': '1',
          'restaurant_id': 'r1',
        },
      }),
    );

    final event = await firstEvent.timeout(const Duration(seconds: 5));
    expect(event.event, 'model.updated');
    expect(event.payload['resource'], 'printers.printjob');
    expect(event.payload['restaurant_id'], 'r1');
  });

  test('envia o JWT no header Authorization', () async {
    final client = RealtimeClient(
      urlBuilder: () => url,
      headersBuilder: () => {'Authorization': 'Bearer jwt-do-login'},
    );
    addTearDown(client.dispose);

    client.start();
    await client.onConnected.first.timeout(const Duration(seconds: 5));
    await waitForServerSocket();

    expect(authorizationHeaders.single, 'Bearer jwt-do-login');
    expect(Uri.parse(url).queryParameters.containsKey('token'), isFalse);
  });

  test('reconecta sozinho quando a conexão cai', () async {
    final client = RealtimeClient(urlBuilder: () => url);
    addTearDown(client.dispose);
    var connections = 0;
    final subscription = client.onConnected.listen((_) => connections++);
    addTearDown(subscription.cancel);

    client.start();
    await client.onConnected.first.timeout(const Duration(seconds: 5));
    await waitForServerSocket();

    // Sem isso o agente ficaria surdo a novos trabalhos até o app reiniciar:
    // uma queda de conexão precisa se recuperar sozinha.
    await serverSockets.single.close();

    await Future.doWhile(() async {
      await Future.delayed(const Duration(milliseconds: 100));
      return connections < 2;
    }).timeout(const Duration(seconds: 15));

    expect(connections, greaterThanOrEqualTo(2));
  });

  test('stop() encerra a conexão e não reconecta mais', () async {
    final client = RealtimeClient(urlBuilder: () => url);
    addTearDown(client.dispose);
    var connections = 0;
    final subscription = client.onConnected.listen((_) => connections++);
    addTearDown(subscription.cancel);

    client.start();
    await client.onConnected.first.timeout(const Duration(seconds: 5));
    await waitForServerSocket();

    client.stop();
    await serverSockets.single.close();
    // Dá tempo suficiente para uma reconexão indevida acontecer, se o timer
    // de backoff não tiver sido cancelado por stop().
    await Future.delayed(const Duration(seconds: 3));

    expect(connections, 1);
  });
}
