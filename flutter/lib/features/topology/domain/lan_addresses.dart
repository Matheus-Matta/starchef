import 'dart:io';

/// Um endereço IPv4 deste computador, com a placa em que ele vive.
class LanAddress {
  const LanAddress({required this.interfaceName, required this.address});

  final String interfaceName;
  final String address;

  /// Faixa privada de rede local (RFC 1918 e link-local).
  ///
  /// É a mesma régua que o relay usa para aceitar uma conexão de entrada:
  /// anunciar um endereço fora dela seria convidar um caixa a conectar num
  /// canal que o próprio principal recusaria como externo.
  bool get isPrivate {
    final parts = address.split('.');
    if (parts.length != 4) return false;
    final octets = parts.map(int.tryParse).toList();
    if (octets.any((value) => value == null || value < 0 || value > 255)) {
      return false;
    }
    final first = octets[0]!;
    final second = octets[1]!;
    return first == 10 ||
        (first == 172 && second >= 16 && second <= 31) ||
        (first == 192 && second == 168) ||
        (first == 169 && second == 254);
  }

  /// A placa é de uma rede virtual do próprio computador.
  ///
  /// Windows com WSL, Hyper-V, Docker, VirtualBox ou um VPN de suporte cria
  /// várias placas com endereço privado que **nenhum outro aparelho da loja
  /// enxerga**. Elas ficam no fim da lista: como os endereços eram ordenados
  /// em ordem alfabética, um `172.20.192.1` de switch virtual vinha antes do
  /// `192.168.0.x` real e virava o endereço do QR Code de pareamento — o
  /// celular lia, tentava, e nunca chegava a lugar nenhum.
  bool get isVirtualAdapter {
    final name = interfaceName.toLowerCase();
    return const [
      'vethernet',
      'hyper-v',
      'wsl',
      'virtualbox',
      'vmware',
      'docker',
      'radmin',
      'hamachi',
      'zerotier',
      'tailscale',
      'tap-',
      'openvpn',
      'loopback',
    ].any(name.contains);
  }
}

/// Por onde os outros caixas alcançam este terminal.
abstract final class LanAddresses {
  /// Endereços utilizáveis, do mais provável para o menos.
  ///
  /// Só endereços de rede privada entram: o relay recusa qualquer origem fora
  /// dela, então um endereço público (ou de VPN de suporte) anunciado aqui
  /// levaria a uma recusa por "origem externa" depois de o operador jurar que
  /// digitou o IP certo.
  static List<String> rank(List<LanAddress> found, int port) {
    final usable = found.where((item) => item.isPrivate).toList()
      ..sort((left, right) {
        final byAdapter = (left.isVirtualAdapter ? 1 : 0).compareTo(
          right.isVirtualAdapter ? 1 : 0,
        );
        if (byAdapter != 0) return byAdapter;
        return left.address.compareTo(right.address);
      });
    final seen = <String>{};
    return [
      for (final item in usable)
        if (seen.add(item.address)) '${item.address}:$port',
    ];
  }

  static Future<List<String>> discover(int port) async {
    try {
      final interfaces = await NetworkInterface.list(
        type: InternetAddressType.IPv4,
        includeLoopback: false,
      );
      return rank([
        for (final interface in interfaces)
          for (final address in interface.addresses)
            LanAddress(
              interfaceName: interface.name,
              address: address.address,
            ),
      ], port);
    } catch (_) {
      return const [];
    }
  }
}
