import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/network/mutation_relay.dart';
import 'package:starchef_pdv/core/network/relay_origin.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

/// As credenciais que o secundário envia ao principal.
///
/// A rede local é autenticada (assinatura HMAC, nonce contra repetição,
/// endereço privado), mas não é criptografada. Um access token em claro no
/// corpo ficaria legível para qualquer um no mesmo segmento — então ele viaja
/// lacrado com a chave de pareamento, que só os dois caixas conhecem.
void main() {
  const secret = 'chave-de-pareamento-da-loja';
  const origin = RelayOrigin(
    accessToken: 'token-do-pdv-2',
    refreshToken: 'refresh-do-pdv-2',
    actorId: 'operador-2',
    actorName: 'Maria',
    installationId: 'instalacao-do-pdv-2',
    terminalName: 'Balcão 02',
  );

  test('o lacre vai e volta inteiro', () {
    final sealed = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );

    final opened = LocalRelayAuthenticator.openOrigin(
      secret: secret,
      sealed: sealed,
    );

    expect(opened, isNotNull);
    expect(opened!.accessToken, origin.accessToken);
    expect(opened.refreshToken, origin.refreshToken);
    expect(opened.actorId, origin.actorId);
    expect(opened.installationId, origin.installationId);
    expect(opened.terminalName, origin.terminalName);
  });

  test('o token não trafega legível', () {
    final sealed = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );

    expect(sealed, isNot(contains('token-do-pdv-2')));
    expect(sealed, isNot(contains('refresh-do-pdv-2')));
    expect(sealed, isNot(contains('operador-2')));
  });

  test('dois lacres da mesma credencial são diferentes', () {
    // Nonce por mensagem: sem ele, duas aberturas iguais produziriam o mesmo
    // texto cifrado e o keystream se repetiria.
    final first = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );
    final second = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );

    expect(first, isNot(second));
  });

  test('quem não tem a chave não abre', () {
    final sealed = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );

    expect(
      LocalRelayAuthenticator.openOrigin(
        secret: 'outra-chave',
        sealed: sealed,
      ),
      isNull,
    );
  });

  test('lacre malformado não derruba o principal', () {
    for (final sealed in ['', 'sem-ponto', 'nonce.nao-e-base64-valido!!', '.']) {
      expect(
        LocalRelayAuthenticator.openOrigin(secret: secret, sealed: sealed),
        isNull,
        reason: 'lacre "$sealed" deveria ser apenas descartado',
      );
    }
  });

  test('credencial incompleta é descartada', () {
    // Sem token ou sem operador não há em nome de quem encaminhar.
    final semToken = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: const RelayOrigin(accessToken: '', actorId: 'operador-2'),
    );

    expect(
      LocalRelayAuthenticator.openOrigin(secret: secret, sealed: semToken),
      isNull,
    );
  });

  test('a origem não aparece em claro no envelope enviado', () {
    final sealed = LocalRelayAuthenticator.sealOrigin(
      secret: secret,
      origin: origin,
    );
    final envelope = RelayMutation(
      method: 'POST',
      path: '/cash-register/open/',
      operationId: 'op-1',
      body: const {'cash_station': 'caixa-1'},
      sealedOrigin: sealed,
    ).toJson();

    expect(envelope['origin'], sealed);
    expect(envelope.toString(), isNot(contains('token-do-pdv-2')));
  });
}
