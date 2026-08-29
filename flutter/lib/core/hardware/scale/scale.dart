import 'dart:async';

import 'scale_device.dart';
import 'scale_sample.dart';
import 'scale_transport.dart';
import 'serial_scale_reader.dart';

/// Dependências compartilhadas por toda leitura de balança do terminal.
///
/// Existe para que uma balança possa ser aberta em qualquer lugar do código
/// com uma linha — `Scale.fromJson(cadastro).open()` — sem cada tela repassar
/// tolerância, papel na trava e transporte de teste.
class ScaleRuntime {
  const ScaleRuntime({
    this.stabilityToleranceKg = 0.002,
    this.silenceTimeout = const Duration(seconds: 4),
    this.role = 'balanca-rapida',
    this.transportFactory,
  });

  /// Variação de peso, em kg, ainda considerada "o mesmo peso".
  ///
  /// Vem das preferências do terminal: é a única coisa da leitura que muda de
  /// máquina para máquina (mesa firme x mesa que balança), enquanto porta,
  /// baud rate e protocolo descrevem o equipamento e ficam no cadastro.
  final double stabilityToleranceKg;

  /// Silêncio tolerado antes de avisar que o equipamento parou de transmitir.
  final Duration silenceTimeout;

  /// Quem aparece como dono na trava entre processos.
  final String role;

  /// Canal de bytes alternativo (testes, sem hardware conectado).
  final ScaleTransport Function(ScaleDevice device)? transportFactory;
}

/// Uma balança pronta para ser lida.
///
/// Esta é a única porta de entrada da leitura de peso no PDV. Ela resolve o
/// cadastro, escolhe o protocolo do fabricante, reserva a porta entre os
/// processos e publica as amostras — na mesma ordem, para qualquer tela. As
/// duas janelas que pesam (a Balança Rápida embutida no PDV e o processo
/// dedicado) usavam cópias da mesma sequência, cada uma lendo os campos do
/// cadastro do seu jeito, e foi assim que o protocolo escolhido no cadastro
/// parou de chegar ao leitor sem que nada na tela dissesse isso.
class Scale {
  Scale(this.device, {this.runtime = const ScaleRuntime()});

  /// Abre a balança direto do cadastro cru (API, cache ou fila local).
  factory Scale.fromJson(
    Map<String, dynamic> scale, {
    ScaleRuntime runtime = const ScaleRuntime(),
  }) => Scale(ScaleDevice.fromJson(scale), runtime: runtime);

  final ScaleDevice device;
  final ScaleRuntime runtime;

  /// O leitor existe desde a construção, não desde [open]: quem vai escutar
  /// peso assina os fluxos antes de mandar abrir a porta, e um fluxo que só
  /// nascesse no `open` perderia as primeiras amostras — e o motivo da falha,
  /// quando a porta nem chega a abrir.
  late final SerialScaleReader? _reader = _build();

  bool _closed = false;

  SerialScaleReader? _build() {
    if (!device.hasPort) return null;
    final factory = runtime.transportFactory;
    if (factory != null) {
      return SerialScaleReader(
        portName: device.port,
        protocol: device.protocol,
        transportFactory: () => factory(device),
        stabilityToleranceKg: runtime.stabilityToleranceKg,
        settleDuration: device.settleDuration,
        zeroThresholdKg: device.zeroThresholdKg,
        silenceTimeout: runtime.silenceTimeout,
        role: runtime.role,
        ownerDetail: device.label,
      );
    }
    return SerialScaleReader.serial(
      portName: device.port,
      baudRate: device.baudRate,
      protocol: device.protocol,
      stabilityToleranceKg: runtime.stabilityToleranceKg,
      settleDuration: device.settleDuration,
      zeroThresholdKg: device.zeroThresholdKg,
      silenceTimeout: runtime.silenceTimeout,
      role: runtime.role,
      ownerDetail: device.label,
    );
  }

  /// Amostras já resolvidas (peso e estabilidade).
  ///
  /// Uma balança sem porta cadastrada devolve um fluxo vazio em vez de nulo:
  /// quem escuta não precisa saber se o cadastro está completo.
  Stream<ScaleSample> get samples =>
      _reader?.samples ?? const Stream<ScaleSample>.empty();

  Stream<ScaleLinkStatus> get statusChanges =>
      _reader?.statusChanges ?? const Stream<ScaleLinkStatus>.empty();

  ScaleLinkStatus get status =>
      _reader?.status ??
      ScaleLinkStatus(
        state: ScaleLinkState.disconnected,
        message: device.missingConfiguration ?? 'Balança não conectada.',
      );

  ScaleSample? get lastSample => _reader?.lastSample;

  /// Peso atual considerado zerado (prato vazio).
  bool get isAtZero => _reader?.isAtZero ?? true;

  /// Abre a porta e começa a receber peso.
  ///
  /// Devolve `false` quando o cadastro não descreve um equipamento
  /// alcançável — sem porta não há o que abrir, e [status] passa a dizer o
  /// que falta cadastrar. Uma porta ocupada ou um cabo solto **não** caem
  /// aqui: o leitor reconecta sozinho e informa pelo [statusChanges].
  Future<bool> open() async {
    final reader = _reader;
    if (reader == null || _closed) return false;
    await reader.start();
    return true;
  }

  /// Pede uma pesagem ao equipamento — o "pegar peso" de emergência.
  Future<ScaleWeightRequest> requestWeight() async =>
      await _reader?.requestWeight() ?? ScaleWeightRequest.unavailable;

  /// Zera a contagem de estabilidade — usado após concluir um pedido.
  void resetStability() => _reader?.resetStability();

  /// Libera a porta. Uma balança fechada não volta a abrir: peça outra.
  ///
  /// Fechar sem nunca ter aberto é barato e correto: construir o leitor não
  /// toca na porta — quem a abre é [open] —, e descartá-lo aqui fecha os
  /// fluxos de quem já tinha assinado.
  Future<void> close() async {
    _closed = true;
    await _reader?.dispose();
  }
}
