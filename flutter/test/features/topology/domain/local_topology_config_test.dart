import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/topology/domain/local_topology_config.dart';

/// A chave de pareamento é escolhida pelo operador — inclusive algo curto
/// como "123", numa rede que ele já confirmou ser privada e confiável. Antes,
/// só uma chave gerada (32 bytes em base64url) passava, e uma chave curta
/// fazia o Caixa Principal nunca abrir a porta da rede local, sem nenhum
/// aviso — só o card de status, que o operador não tinha motivo de reabrir.
void main() {
  LocalTopologyConfig principal({
    required String pairingSecret,
    bool trustedNetworkAcknowledged = true,
  }) => LocalTopologyConfig(
    mode: LocalTopologyMode.principal,
    nodeId: 'caixa-1',
    port: 47832,
    pairingSecret: pairingSecret,
    trustedNetworkAcknowledged: trustedNetworkAcknowledged,
  );

  group('lanSharingErrors', () {
    test('aceita uma chave curta escolhida pelo operador', () {
      expect(principal(pairingSecret: '123').lanSharingErrors(), isEmpty);
    });

    test('recusa chave vazia', () {
      expect(
        principal(pairingSecret: '').lanSharingErrors(),
        contains(contains('Defina uma chave')),
      );
    });

    test('recusa sem confirmar a rede privada e confiável', () {
      expect(
        principal(
          pairingSecret: '123',
          trustedNetworkAcknowledged: false,
        ).lanSharingErrors(),
        contains(contains('rede privada e confiável')),
      );
    });
  });
}
