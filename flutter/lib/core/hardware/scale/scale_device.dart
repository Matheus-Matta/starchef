import 'scale_protocol.dart';

/// A balança como ela está cadastrada, resolvida uma única vez.
///
/// O cadastro chega como `Map<String, dynamic>` do backend, do cache local ou
/// da fila em disco, e cada tela lia esses campos por conta própria — foi
/// assim que o protocolo escolhido no cadastro deixou de chegar ao leitor: a
/// estação lia `settings['protocol']`, mas a tela de equipamentos grava
/// `protocol` no topo do registro (é um campo do modelo, com as opções
/// `generic`, `toledo_prt2`, `filizola` e `urano`). O resultado era uma
/// balança Urano lida com o decodificador genérico, sem que nada na tela
/// dissesse isso.
///
/// Aqui a leitura do cadastro é uma só, e é ela que vale para o leitor, para
/// o cartão de configuração da estação e para qualquer tela futura.
class ScaleDevice {
  ScaleDevice._({
    required this.raw,
    required this.id,
    required this.name,
    required this.port,
    required this.baudRate,
    required this.protocol,
    required this.settleDuration,
    required this.zeroThresholdKg,
    required this.productId,
    required this.printerId,
  });

  factory ScaleDevice.fromJson(Map<String, dynamic> scale) {
    final settings = scale['settings'] as Map<String, dynamic>? ?? const {};
    return ScaleDevice._(
      raw: scale,
      id: '${scale['id'] ?? ''}'.trim(),
      name: '${scale['name'] ?? ''}'.trim(),
      port: '${scale['port'] ?? ''}'.trim(),
      // `baudrate` mora em `settings` porque não é campo do modelo — é a tela
      // de equipamentos que o grava lá.
      baudRate:
          int.tryParse('${settings['baudrate'] ?? scale['baudrate'] ?? ''}') ??
          9600,
      // O campo do modelo manda. `settings['protocol']` continua sendo lido
      // como segunda opção para não invalidar registros antigos que o
      // gravaram lá à mão pelo JSON de configurações avançadas.
      protocol: ScaleProtocol.forId(
        _firstFilled([scale['protocol'], settings['protocol']]),
      ),
      settleDuration: Duration(
        seconds:
            int.tryParse('${scale['auto_print_delay_seconds'] ?? ''}') ?? 3,
      ),
      zeroThresholdKg:
          double.tryParse('${settings['zero_threshold_kg'] ?? ''}') ?? 0.005,
      productId: '${scale['product'] ?? ''}'.trim(),
      printerId: '${scale['printer'] ?? ''}'.trim(),
    );
  }

  /// Primeiro valor preenchido da lista.
  ///
  /// Um campo em branco é tão ausente quanto um campo nulo aqui: o backend
  /// grava `''` num `CharField` que ninguém preencheu, e `??` sozinho pararia
  /// nele em vez de cair na segunda opção.
  static String? _firstFilled(List<Object?> values) {
    for (final value in values) {
      final text = '${value ?? ''}'.trim();
      if (text.isNotEmpty) return text;
    }
    return null;
  }

  /// Cadastro original, para quem ainda fala em `Map` (fila local e API).
  final Map<String, dynamic> raw;

  final String id;
  final String name;

  /// Porta serial cadastrada (`COM3`, `/dev/ttyUSB0`).
  final String port;

  final int baudRate;

  /// Decodificador dos quadros deste fabricante.
  final ScaleProtocol protocol;

  /// Quanto tempo o peso precisa ficar parado para valer como estável.
  final Duration settleDuration;

  /// Abaixo deste peso o prato é considerado vazio.
  final double zeroThresholdKg;

  final String productId;
  final String printerId;

  bool get hasPort => port.isNotEmpty;

  /// Recurso disputado por todos os processos que leem este equipamento.
  ///
  /// É o endereço físico, não o `id` do cadastro: duas balanças cadastradas
  /// separadamente podem apontar para a mesma porta, e nesse caso continuam
  /// sendo um equipamento só — que não aceita duas aberturas ao mesmo tempo.
  String get lockResource => 'scale:$port';

  /// Como esta balança aparece num aviso na tela.
  String get label => name.isEmpty ? (hasPort ? port : 'balança') : name;

  /// O que falta cadastrar para a leitura automática funcionar.
  String? get missingConfiguration => hasPort
      ? null
      : 'A balança não tem porta serial cadastrada. Informe a COM e o baud '
            'rate no cadastro para ler o peso automaticamente.';

  /// Resumo exibido no cartão de configuração da estação.
  String get summary =>
      '$baudRate baud · ${protocol.label} · estabiliza em '
      '${settleDuration.inSeconds} s';
}
