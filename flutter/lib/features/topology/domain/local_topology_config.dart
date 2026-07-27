import 'dart:convert';

enum LocalTopologyMode { standalone, principal, client }

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

  List<String> validate() {
    final errors = <String>[];
    if (nodeId.trim().isEmpty) errors.add('Identificador do caixa ausente.');
    if (port < 1024 || port > 65535) {
      errors.add('A porta deve ficar entre 1024 e 65535.');
    }
    if (mode == LocalTopologyMode.client &&
        principalHost.trim().isEmpty) {
      errors.add('Informe o IP ou nome do Caixa Principal.');
    }
    if (mode == LocalTopologyMode.client &&
        !_isValidHost(principalHost.trim())) {
      errors.add(
        'Informe apenas um IP ou nome de rede, sem protocolo, porta ou caminho.',
      );
    }
    if (mode != LocalTopologyMode.standalone &&
        !_isStrongPairingSecret(pairingSecret.trim())) {
      errors.add('Use uma chave segura de 32 bytes gerada pelo aplicativo.');
    }
    if (mode != LocalTopologyMode.standalone &&
        !trustedNetworkAcknowledged) {
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

  static LocalTopologyMode modeFrom(String? value) => switch (value) {
    'principal' => LocalTopologyMode.principal,
    'client' => LocalTopologyMode.client,
    _ => LocalTopologyMode.standalone,
  };
}

extension LocalTopologyModeLabel on LocalTopologyMode {
  String get storageValue => switch (this) {
    LocalTopologyMode.standalone => 'standalone',
    LocalTopologyMode.principal => 'principal',
    LocalTopologyMode.client => 'client',
  };

  String get label => switch (this) {
    LocalTopologyMode.standalone => 'Independente',
    LocalTopologyMode.principal => 'Caixa Principal',
    LocalTopologyMode.client => 'Caixa Cliente',
  };
}
