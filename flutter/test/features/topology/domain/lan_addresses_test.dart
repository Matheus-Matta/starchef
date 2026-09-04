import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/features/topology/domain/lan_addresses.dart';

void main() {
  test('a rede real vem antes das placas virtuais do Windows', () {
    // Uma máquina comum de balcão com WSL, Hyper-V e um VPN de suporte
    // instalados: cinco endereços privados, e só um deles alcançável pelos
    // outros aparelhos da loja. Em ordem alfabética o QR Code de pareamento
    // anunciava `172.20.192.1` — o celular lia e tentava um switch virtual.
    final ranked = LanAddresses.rank(const [
      LanAddress(interfaceName: 'vEthernet (WSL)', address: '172.20.192.1'),
      LanAddress(
        interfaceName: 'vEthernet (Default Switch)',
        address: '172.26.112.1',
      ),
      LanAddress(interfaceName: 'Ethernet', address: '192.168.100.12'),
      LanAddress(interfaceName: 'VirtualBox Host-Only', address: '192.168.48.1'),
    ], 47832);

    expect(ranked.first, '192.168.100.12:47832');
    expect(ranked, hasLength(4));
  });

  test('endereço fora da rede privada não é anunciado', () {
    // O relay recusa qualquer origem que não seja privada. Anunciar o IP de
    // um VPN de suporte levava o operador a jurar que digitou o IP certo e
    // receber "origem externa recusada" do outro lado.
    final ranked = LanAddresses.rank(const [
      LanAddress(interfaceName: 'Radmin VPN', address: '26.164.133.87'),
      LanAddress(interfaceName: 'Wi-Fi', address: '10.0.0.30'),
    ], 47832);

    expect(ranked, ['10.0.0.30:47832']);
  });

  test('sem endereço privado nenhum, a lista fica vazia', () {
    expect(
      LanAddresses.rank(const [
        LanAddress(interfaceName: 'Ethernet', address: '200.10.1.5'),
      ], 47832),
      isEmpty,
    );
  });
}
