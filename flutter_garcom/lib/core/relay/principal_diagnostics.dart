import 'dart:async';
import 'dart:io';

import '../network/api_exception.dart';
import 'principal_client.dart';

/// Resultado de um passo do diagnóstico.
class ProbeStep {
  const ProbeStep({
    required this.name,
    required this.ok,
    required this.detail,
    this.elapsed,
  });

  final String name;
  final bool ok;
  final String detail;
  final Duration? elapsed;

  @override
  String toString() {
    final tempo = elapsed == null ? '' : ' (${elapsed!.inMilliseconds} ms)';
    return '${ok ? 'OK ' : 'FALHOU'} $name$tempo: $detail';
  }
}

/// Testa a ligação com o Caixa Principal passo a passo.
///
/// Existe porque "erro de conexão" na tela não diz onde parou. São problemas
/// completamente diferentes com a mesma cara: o aparelho não alcançou o
/// computador (firewall, Wi-Fi, VPN), alcançou mas ninguém atendeu na porta
/// (PDV fechado ou sem a rede local ligada), ou atendeu e recusou (chave,
/// relógio, restaurante). Cada um tem um culpado e uma correção diferentes.
class PrincipalDiagnostics {
  PrincipalDiagnostics({required this.client});

  final PrincipalClient client;

  Future<List<ProbeStep>> run(
    PrincipalConfig config,
    RelayIdentity identity,
  ) async {
    final steps = <ProbeStep>[];

    final erros = config.validate();
    steps.add(
      ProbeStep(
        name: 'Endereço informado',
        ok: erros.isEmpty,
        detail: erros.isEmpty
            ? '${config.host}:${config.port}'
            : erros.join(' '),
      ),
    );
    if (erros.isNotEmpty) return steps;

    steps.add(
      ProbeStep(
        name: 'Identificação do garçom',
        ok: identity.isComplete,
        detail: identity.isComplete
            ? 'restaurante ${identity.restaurantId}'
            : 'sessão sem conta, operador ou restaurante',
      ),
    );
    if (!identity.isComplete) return steps;

    // TCP puro antes de qualquer HTTP: é o que separa "a rede não deixa
    // chegar" de "chegou e a resposta não serviu".
    final tcp = await _tcp(config);
    steps.add(tcp);
    if (!tcp.ok) return steps;

    steps.add(await _health(config, identity));
    return steps;
  }

  Future<ProbeStep> _tcp(PrincipalConfig config) async {
    final relogio = Stopwatch()..start();
    try {
      final socket = await Socket.connect(
        config.host.trim(),
        config.port,
        timeout: const Duration(seconds: 4),
      );
      final local = socket.address.address;
      socket.destroy();
      return ProbeStep(
        name: 'Alcance na rede (TCP)',
        ok: true,
        detail: 'conectou — este aparelho é $local',
        elapsed: relogio.elapsed,
      );
    } on SocketException catch (error) {
      // A distinção importa: "recusada" é alguém dizendo não (nada escutando
      // na porta); silêncio até o tempo acabar é firewall ou rede errada.
      final recusada =
          error.osError?.errorCode == 61 ||
          error.osError?.errorCode == 111 ||
          error.osError?.errorCode == 10061 ||
          '${error.osError?.message}'.toLowerCase().contains('recus');
      return ProbeStep(
        name: 'Alcance na rede (TCP)',
        ok: false,
        elapsed: relogio.elapsed,
        detail: recusada
            ? 'a máquina respondeu mas NADA está escutando na porta '
                  '${config.port}. O PDV está aberto e com a rede local '
                  'ligada (Configurações → Rede local)?'
            : 'sem resposta de ${config.host}:${config.port}. Firewall do '
                  'Windows bloqueando, aparelho em outro Wi-Fi, ou VPN ligada '
                  'no celular.',
      );
    } on TimeoutException {
      return ProbeStep(
        name: 'Alcance na rede (TCP)',
        ok: false,
        elapsed: relogio.elapsed,
        detail:
            'tempo esgotado em ${config.host}:${config.port} — o pacote sai '
            'e não volta. É o sintoma clássico de firewall.',
      );
    }
  }

  Future<ProbeStep> _health(
    PrincipalConfig config,
    RelayIdentity identity,
  ) async {
    final relogio = Stopwatch()..start();
    try {
      final ok = await client.health(config, identity);
      return ProbeStep(
        name: 'Pareamento (assinatura)',
        ok: ok,
        elapsed: relogio.elapsed,
        detail: ok
            ? 'o Caixa Principal aceitou este aparelho'
            : 'o caixa respondeu, mas não confirmou o pareamento',
      );
    } on PrincipalUnavailable catch (error) {
      return ProbeStep(
        name: 'Pareamento (assinatura)',
        ok: false,
        elapsed: relogio.elapsed,
        detail:
            '${error.message} '
            '(a resposta não foi assinada com esta chave — normalmente é a '
            'chave errada)',
      );
    } on ApiException catch (error) {
      // Aqui a resposta veio assinada: a chave está CERTA e o motivo é o que
      // o próprio Caixa Principal informou.
      return ProbeStep(
        name: 'Pareamento (assinatura)',
        ok: false,
        elapsed: relogio.elapsed,
        detail:
            'chave confere; o caixa recusou com '
            '${error.statusCode ?? '-'}: ${error.message}',
      );
    }
  }
}
