import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/topology/services/local_topology_service.dart';

/// O Caixa Principal abre a porta em todas as interfaces, então este filtro é
/// o que garante que ele só conversa com a rede da loja.
void main() {
  bool accepts(String address) =>
      LocalTopologyService.isLocalNetworkAddress(InternetAddress(address));

  group('aceita a rede local', () {
    test('as três faixas privadas de IPv4', () {
      expect(accepts('10.0.0.5'), isTrue);
      expect(accepts('10.255.255.254'), isTrue);
      expect(accepts('172.16.0.1'), isTrue);
      expect(accepts('172.31.255.254'), isTrue);
      expect(accepts('192.168.1.10'), isTrue);
    });

    test('o próprio terminal, em qualquer família', () {
      // Loopback é a própria máquina: quem já executa código aqui não ganha
      // nada passando por esta porta.
      expect(accepts('127.0.0.1'), isTrue);
      expect(accepts('::1'), isTrue);
    });

    test('link-local, que é o que sobra quando o DHCP falha', () {
      // Dois caixas ligados direto ainda precisam se enxergar.
      expect(accepts('169.254.10.20'), isTrue);
    });
  });

  group('recusa qualquer origem de fora', () {
    test('endereços públicos', () {
      expect(accepts('8.8.8.8'), isFalse);
      expect(accepts('1.1.1.1'), isFalse);
      expect(accepts('203.0.113.7'), isFalse);
    });

    test('as bordas das faixas privadas não vazam', () {
      // 172.15 e 172.32 estão fora da faixa 172.16–172.31.
      expect(accepts('172.15.255.255'), isFalse);
      expect(accepts('172.32.0.1'), isFalse);
      // 192.169 não é 192.168.
      expect(accepts('192.169.1.1'), isFalse);
      // 11.x não é 10.x.
      expect(accepts('11.0.0.1'), isFalse);
    });

    test('IPv6 que não seja o próprio terminal', () {
      // A topologia é IPv4 e o socket nem escuta em IPv6; aceitar uma família
      // que ninguém usa só ampliaria a superfície.
      expect(accepts('fd00::1'), isFalse);
      expect(accepts('fe80::1'), isFalse);
      expect(accepts('2001:4860:4860::8888'), isFalse);
    });

    test('origem desconhecida', () {
      // `connectionInfo` nulo não pode ser tratado como confiável.
      expect(LocalTopologyService.isLocalNetworkAddress(null), isFalse);
    });
  });
}
