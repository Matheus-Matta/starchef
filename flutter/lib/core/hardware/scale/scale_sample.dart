/// Uma leitura de peso decodificada diretamente do equipamento.
class ScaleSample {
  ScaleSample({
    required this.weightKg,
    required this.raw,
    this.stable,
    this.negative = false,
    this.hasWeight = true,
    DateTime? at,
  }) : at = at ?? DateTime.now();

  /// Peso líquido em quilogramas.
  final double weightKg;

  /// Quadro original, preservado para diagnóstico de firmware.
  final String raw;

  /// Estabilidade informada pelo próprio protocolo.
  ///
  /// `null` quando o equipamento não transmite esse bit — nesse caso quem
  /// decide é o leitor, comparando leituras consecutivas.
  final bool? stable;

  /// Indica se a amostra contém um peso válido enviado pelo equipamento.
  /// `true` por padrão; `false` significa que o quadro trouxe apenas
  /// informação de estabilidade/status sem valor numérico.
  final bool hasWeight;

  /// Peso negativo indica prato retirado ou necessidade de tara.
  final bool negative;

  final DateTime at;

  @override
  String toString() =>
      'ScaleSample(${weightKg.toStringAsFixed(3)} kg, stable: $stable, hasWeight: $hasWeight)';
}

/// Resultado de um pedido manual de pesagem.
enum ScaleWeightRequest {
  /// A solicitação foi enviada; a resposta chega pelo fluxo de amostras.
  sent,

  /// O canal está aberto, mas em modo somente leitura — o driver ou a porta
  /// recusaram escrita. Balanças de transmissão contínua seguem funcionando.
  writeNotSupported,

  /// Não foi possível abrir a porta para falar com o equipamento.
  notConnected,

  /// A estação não está em operação ou não tem porta configurada.
  unavailable,
}

/// Situação da ligação com a balança, exibida ao operador.
enum ScaleLinkState {
  /// Abrindo a porta ou aguardando o primeiro quadro válido.
  connecting,

  /// Porta aberta e quadros chegando.
  connected,

  /// Porta fechada por configuração ausente ou desconexão solicitada.
  disconnected,

  /// Porta aberta, mas o equipamento parou de transmitir.
  noResponse,

  /// Quadros chegando, porém ilegíveis para o protocolo escolhido.
  readError,

  /// A porta já está reservada por outra janela ou processo.
  portBusy,
}

/// Estado publicado pelo leitor serial da balança.
class ScaleLinkStatus {
  const ScaleLinkStatus({
    required this.state,
    required this.message,
    this.portName,
    this.lastSampleAt,
    this.owner,
  });

  final ScaleLinkState state;
  final String message;
  final String? portName;
  final DateTime? lastSampleAt;

  /// Quem detém a porta quando o estado é [ScaleLinkState.portBusy].
  final String? owner;

  bool get isConnected => state == ScaleLinkState.connected;

  @override
  bool operator ==(Object other) =>
      other is ScaleLinkStatus &&
      state == other.state &&
      message == other.message &&
      portName == other.portName &&
      lastSampleAt == other.lastSampleAt &&
      owner == other.owner;

  @override
  int get hashCode =>
      Object.hash(state, message, portName, lastSampleAt, owner);
}
