import 'dart:convert';

/// Papel deste terminal na rede local da loja.
///
/// Não existe mais um modo "independente". Todo terminal é Caixa Principal ou
/// Caixa Cliente, porque é o principal que fala com a nuvem: sem ele definido,
/// dois terminais sincronizariam por conta própria e voltariam a divergir. Um
/// restaurante com um só caixa simplesmente tem esse caixa como principal.
enum LocalTopologyMode { principal, client }

class LocalTopologyConfig {
  const LocalTopologyConfig({
    required this.mode,
    required this.nodeId,
    required this.port,
    required this.pairingSecret,
    this.trustedNetworkAcknowledged = false,
    this.principalHost = '',
  });

  static const defaultPort = 47832;

  final LocalTopologyMode mode;
  final String nodeId;
  final String principalHost;
  final int port;
  final String pairingSecret;
  final bool trustedNetworkAcknowledged;

  String get endpoint => 'http://${principalHost.trim()}:$port';

  LocalTopologyConfig copyWith({
    LocalTopologyMode? mode,
    String? nodeId,
    String? principalHost,
    int? port,
    String? pairingSecret,
    bool? trustedNetworkAcknowledged,
  }) => LocalTopologyConfig(
    mode: mode ?? this.mode,
    nodeId: nodeId ?? this.nodeId,
    principalHost: principalHost ?? this.principalHost,
    port: port ?? this.port,
    pairingSecret: pairingSecret ?? this.pairingSecret,
    trustedNetworkAcknowledged:
        trustedNetworkAcknowledged ?? this.trustedNetworkAcknowledged,
  );

  /// Problemas que impedem o terminal de operar neste modo.
  List<String> validate() {
    final errors = <String>[];
    if (nodeId.trim().isEmpty) errors.add('Identificador do caixa ausente.');
    if (port < 1024 || port > 65535) {
      errors.add('A porta deve ficar entre 1024 e 65535.');
    }
    if (mode == LocalTopologyMode.client) {
      if (principalHost.trim().isEmpty) {
        errors.add('Informe o IP ou nome do Caixa Principal.');
      } else if (!_isValidHost(principalHost.trim())) {
        errors.add(
          'Informe apenas um IP ou nome de rede, sem protocolo, porta ou '
          'caminho.',
        );
      }
      // Sem chave e sem confirmação da rede, o cliente não consegue nem
      // assinar uma requisição ao principal.
      errors.addAll(lanSharingErrors());
    }
    return errors;
  }

  /// Requisitos para o Caixa Principal abrir a porta e atender outros caixas.
  ///
  /// Ficam separados dos erros de [validate] porque um restaurante de um caixa
  /// só não precisa de nada disso: ele opera e sincroniza com a nuvem
  /// normalmente, apenas sem servir a rede local.
  List<String> lanSharingErrors() {
    final errors = <String>[];
    if (!_isStrongPairingSecret(pairingSecret.trim())) {
      errors.add('Gere a chave de pareamento para conectar outros caixas.');
    }
    if (!trustedNetworkAcknowledged) {
      errors.add(
        'Confirme que os caixas estão em uma rede privada e confiável.',
      );
    }
    return errors;
  }

  static bool _isStrongPairingSecret(String value) {
    try {
      return base64Url.decode(base64Url.normalize(value)).length == 32;
    } on FormatException {
      return false;
    }
  }

  static bool _isValidHost(String value) =>
      value.isNotEmpty &&
      value.length <= 253 &&
      !value.contains(RegExp(r'[\s/:@?#\\]')) &&
      RegExp(r'^[A-Za-z0-9.-]+$').hasMatch(value) &&
      !value.startsWith('.') &&
      !value.endsWith('.') &&
      !value.contains('..');

  /// Lê o modo gravado. Instalações antigas em `standalone` viram principal:
  /// um terminal sozinho é o principal da própria loja, e assim ele mantém a
  /// responsabilidade de sincronizar com a nuvem.
  static LocalTopologyMode modeFrom(String? value) => switch (value) {
    'client' => LocalTopologyMode.client,
    _ => LocalTopologyMode.principal,
  };
}

extension LocalTopologyModeLabel on LocalTopologyMode {
  String get storageValue => switch (this) {
    LocalTopologyMode.principal => 'principal',
    LocalTopologyMode.client => 'client',
  };

  String get label => switch (this) {
    LocalTopologyMode.principal => 'Caixa Principal',
    LocalTopologyMode.client => 'Caixa Cliente',
  };
}
