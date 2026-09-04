import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/relay/relay_signature.dart';

/// Reimplementação independente da assinatura, escrita a partir do PDV
/// (`LocalRelayAuthenticator`, em
/// `flutter/lib/features/topology/services/local_topology_service.dart`).
///
/// O teste compara a nossa função com esta — se alguém mudar a ordem dos
/// campos ou o separador de um lado só, o Caixa Principal passaria a devolver
/// 401 em tudo, e é bem mais barato descobrir isso aqui.
String pdvSignature({
  required String secret,
  required String method,
  required String path,
  required int timestamp,
  required String nonce,
  required String account,
  required String actor,
  required String restaurant,
  required String nodeId,
  required String body,
}) {
  final canonical = [
    method.toUpperCase(),
    path,
    '$timestamp',
    nonce,
    account,
    actor,
    restaurant,
    nodeId,
    body,
  ].join('\n');
  final digest = Hmac(sha256, utf8.encode(secret)).convert(utf8.encode(canonical));
  return base64UrlEncode(digest.bytes).replaceAll('=', '');
}

void main() {
  group('assinatura da requisição', () {
    test('bate com a implementação do Caixa Principal', () {
      final ours = RelaySignature.request(
        secret: 'w4Uu9k1Z2mN0pQ8rS6tV5xY3zA7bC1dE2fG4hJ6kL8M=',
        method: 'post',
        path: '/v1/relay',
        timestamp: 1755900000,
        nonce: 'nonce-de-teste-1234',
        account: 'conta-1',
        actor: 'garcom-1',
        restaurant: 'restaurante-1',
        nodeId: 'aparelho-1',
        body: '{"method":"POST"}',
      );

      expect(
        ours,
        pdvSignature(
          secret: 'w4Uu9k1Z2mN0pQ8rS6tV5xY3zA7bC1dE2fG4hJ6kL8M=',
          method: 'POST',
          path: '/v1/relay',
          timestamp: 1755900000,
          nonce: 'nonce-de-teste-1234',
          account: 'conta-1',
          actor: 'garcom-1',
          restaurant: 'restaurante-1',
          nodeId: 'aparelho-1',
          body: '{"method":"POST"}',
        ),
      );
    });

    test('não usa padding base64 (o principal compara texto puro)', () {
      final signature = RelaySignature.request(
        secret: 'segredo',
        method: 'GET',
        path: '/v1/health',
        timestamp: 1,
        nonce: 'n' * 12,
        account: 'a',
        actor: 'b',
        restaurant: 'c',
        nodeId: 'd',
        body: '',
      );
      expect(signature.contains('='), isFalse);
      expect(signature, isNotEmpty);
    });

    test('qualquer campo diferente muda a assinatura', () {
      String sign({String actor = 'garcom-1', String body = ''}) =>
          RelaySignature.request(
            secret: 'segredo',
            method: 'POST',
            path: '/v1/relay',
            timestamp: 1755900000,
            nonce: 'nonce-de-teste-1234',
            account: 'conta-1',
            actor: actor,
            restaurant: 'restaurante-1',
            nodeId: 'aparelho-1',
            body: body,
          );

      expect(sign(), isNot(sign(actor: 'garcom-2')));
      expect(sign(), isNot(sign(body: '{}')));
    });
  });

  group('assinatura da resposta', () {
    test('depende do nonce, do status e do corpo', () {
      String sign({int status = 200, String body = '{"ok":true}'}) =>
          RelaySignature.response(
            secret: 'segredo',
            requestNonce: 'nonce-de-teste-1234',
            statusCode: status,
            body: body,
          );

      expect(sign(), sign());
      expect(sign(), isNot(sign(status: 401)));
      expect(sign(), isNot(sign(body: '{"ok":false}')));
    });
  });

  group('comparação em tempo constante', () {
    test('reconhece iguais e recusa diferentes', () {
      expect(RelaySignature.constantTimeEquals('abc', 'abc'), isTrue);
      expect(RelaySignature.constantTimeEquals('abc', 'abd'), isFalse);
      expect(RelaySignature.constantTimeEquals('abc', 'abcd'), isFalse);
      expect(RelaySignature.constantTimeEquals('', ''), isTrue);
    });
  });

  group('identificador aleatório', () {
    test('serve como nonce para o principal (mínimo de 8 caracteres)', () {
      final ids = List.generate(50, (_) => RelaySignature.randomId());
      expect(ids.toSet().length, ids.length, reason: 'não pode repetir');
      for (final id in ids) {
        expect(id.length, greaterThanOrEqualTo(8));
        // Formato aceito pelo `operation_id` do relay: [A-Za-z0-9._:-].
        expect(RegExp(r'^[A-Za-z0-9._:-]{8,160}$').hasMatch(id), isTrue);
      }
    });
  });
}
