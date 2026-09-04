import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/relay/principal_client.dart';
import 'package:starchef_garcom/core/relay/principal_diagnostics.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';

/// O diagnóstico existe para separar três falhas que apareciam como a mesma
/// frase na tela ("erro de conexão"), cada uma com um culpado diferente:
///
/// 1. o aparelho não alcança o computador — firewall, Wi-Fi errado, VPN;
/// 2. alcança, mas nada atende na porta — PDV fechado ou rede local desligada;
/// 3. atende e recusa — chave, relógio ou restaurante.
void main() {
  const identity = RelayIdentity(
    accountId: 'conta-1',
    actorId: 'garcom-1',
    restaurantId: 'restaurante-1',
  );
  const secret = 'chave-de-pareamento';

  late PrincipalDiagnostics diagnostics;

  setUp(() => diagnostics = PrincipalDiagnostics(client: PrincipalClient()));

  PrincipalConfig config(int port, {String key = secret, String host = '127.0.0.1'}) =>
      PrincipalConfig(host: host, port: port, secret: key, nodeId: 'aparelho-teste');

  test('endereço inválido para antes de tocar na rede', () async {
    final steps = await diagnostics.run(
      config(47832, host: 'http://192.168.0.10'),
      identity,
    );

    expect(steps, hasLength(1));
    expect(steps.single.ok, isFalse);
    expect(steps.single.name, contains('Endereço'));
  });

  test('sessão incompleta para antes de tocar na rede', () async {
    final steps = await diagnostics.run(
      config(47832),
      const RelayIdentity(
        accountId: 'conta-1',
        actorId: '',
        restaurantId: 'restaurante-1',
      ),
    );

    expect(steps.last.ok, isFalse);
    expect(steps.last.name, contains('Identificação'));
  });

  test('porta fechada é apontada como "ninguém escutando"', () async {
    // Porta livre e sem servidor: a máquina existe e recusa a conexão.
    final socket = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final porta = socket.port;
    await socket.close();

    final steps = await diagnostics.run(config(porta), identity);

    final tcp = steps.firstWhere((step) => step.name.contains('TCP'));
    expect(tcp.ok, isFalse);
    expect(tcp.detail, contains('NADA está escutando'));
    // Não faz sentido testar assinatura se nem a porta abriu.
    expect(steps.any((step) => step.name.contains('Pareamento')), isFalse);
  });

  test('caixa respondendo e chave certa: todos os passos passam', () async {
    final server = await _principal(secret: secret);
    addTearDown(() => server.close(force: true));

    final steps = await diagnostics.run(config(server.port), identity);

    expect(steps.every((step) => step.ok), isTrue, reason: '$steps');
    expect(steps.last.detail, contains('aceitou este aparelho'));
  });

  test('chave errada aponta a chave, não a rede', () async {
    final server = await _principal(secret: secret);
    addTearDown(() => server.close(force: true));

    final steps = await diagnostics.run(
      config(server.port, key: 'chave-que-nao-e-a-do-caixa'),
      identity,
    );

    final tcp = steps.firstWhere((step) => step.name.contains('TCP'));
    expect(tcp.ok, isTrue, reason: 'a rede está boa: o problema é outro');
    expect(steps.last.ok, isFalse);
    expect(steps.last.detail, contains('chave errada'));
  });

  test('recusa do caixa com a chave certa mostra o motivo dele', () async {
    final server = await _principal(
      secret: secret,
      status: HttpStatus.unauthorized,
      detail: 'Este caixa está operando outro restaurante.',
    );
    addTearDown(() => server.close(force: true));

    final steps = await diagnostics.run(config(server.port), identity);

    expect(steps.last.ok, isFalse);
    // A distinção que resolve o chamado: a chave confere, o motivo é outro.
    expect(steps.last.detail, contains('chave confere'));
    expect(steps.last.detail, contains('outro restaurante'));
  });
}

/// Caixa Principal de mentira, com resposta assinada como a do PDV.
Future<HttpServer> _principal({
  required String secret,
  int status = HttpStatus.ok,
  String? detail,
}) async {
  final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
  server.listen((request) async {
    await utf8.decoder.bind(request).join();
    final nonce = request.headers.value('x-starchef-nonce') ?? '';
    final payload = jsonEncode(
      status == HttpStatus.ok ? {'ok': true} : {'detail': detail},
    );
    request.response
      ..statusCode = status
      ..headers.contentType = ContentType.json
      ..headers.set(
        'x-starchef-response-signature',
        RelaySignature.response(
          secret: secret,
          requestNonce: nonce,
          statusCode: status,
          body: payload,
        ),
      )
      ..write(payload);
    await request.response.close();
  });
  return server;
}
