import 'dart:async';
import 'dart:io';

import 'package:flutter_libserialport/flutter_libserialport.dart';

import '../../../core/hardware/peripheral_lock.dart';
import '../../../core/logging/app_logger.dart';
import '../domain/printer_endpoint.dart';
import 'escpos_codec.dart';
import 'print_document.dart';
import 'printer_device.dart';
import 'printer_transport.dart';

enum PrinterAvailabilityPhase { checking, available, unavailable, notConfigured }

class PrinterAvailability {
  const PrinterAvailability(this.phase, this.message);

  final PrinterAvailabilityPhase phase;
  final String message;

  bool get isAvailable => phase == PrinterAvailabilityPhase.available;

  static const checking = PrinterAvailability(
    PrinterAvailabilityPhase.checking,
    'Verificando impressora...',
  );
  static const available = PrinterAvailability(
    PrinterAvailabilityPhase.available,
    'Impressora disponível',
  );
  static const disconnected = PrinterAvailability(
    PrinterAvailabilityPhase.unavailable,
    'Impressora desconectada',
  );
  static const notConfigured = PrinterAvailability(
    PrinterAvailabilityPhase.notConfigured,
    'Impressora desconectada',
  );
}

/// Dependências compartilhadas por toda impressão do terminal.
///
/// Existe para que uma impressora possa ser construída em qualquer lugar do
/// código com uma linha — `KitchenPrinter(device).send(documento)` — sem cada
/// tela ter de repassar pausas, sondas e publicação de status.
class PrinterRuntime {
  const PrinterRuntime({
    this.timing = const PrintTiming(),
    this.networkWriter,
    this.availabilityProbe,
    this.onStatus,
    this.lockTimeout = const Duration(seconds: 10),
  });

  final PrintTiming timing;

  /// Escrita de rede alternativa (testes).
  final Future<void> Function(PrinterEndpoint target, List<int> bytes)?
  networkWriter;

  /// Checagem de presença alternativa (testes).
  final Future<bool> Function(PrinterEndpoint target)? availabilityProbe;

  /// Para onde vai o estado visível na tela de vendas.
  final void Function(PrinterAvailability status)? onStatus;

  /// Quanto tempo um trabalho espera a vez no mesmo equipamento.
  ///
  /// Uma rajada de comandas do mesmo setor sai uma atrás da outra na mesma
  /// impressora; esperar a vez é o comportamento correto, desistir na hora
  /// não é.
  final Duration lockTimeout;
}

/// Uma impressora pronta para receber um documento.
///
/// Esta é a única porta de entrada da impressão no PDV. [send] resolve o
/// cadastro, escolhe o protocolo, reserva o equipamento, monta os bytes,
/// entrega e traduz a falha — nessa ordem, para qualquer tipo de cupom.
///
/// Cada tipo de impressão é uma subclasse ([ReceiptPrinter], [KitchenPrinter],
/// [TestPrinter], ...). Elas não reimplementam nada do envio: só declaram o
/// que aquele cupom é (o `job_type` gravado na fila) e como uma falha dele
/// deve ser tratada. Antes essa distinção estava espalhada em cada tela, e
/// era por isso que o recibo de venda tinha um caminho de erro e a comanda
/// automática tinha outro.
abstract class Printer {
  Printer(this.device, {this.runtime = const PrinterRuntime()});

  /// Escolhe a subclasse pelo tipo do documento, a partir do cadastro cru
  /// (API, cache em memória ou fila local).
  ///
  /// É o caminho da fila: o que está no disco é um `job_type` em texto, e
  /// quem imprime precisa da mesma classe que teria sido usada na origem.
  static Printer forDocument(
    Map<String, dynamic> printer,
    PrintDocument document, {
    PrinterRuntime runtime = const PrinterRuntime(),
  }) {
    final device = PrinterDevice.fromJson(printer);
    return switch (document.type) {
      PrintJobType.receipt => ReceiptPrinter(device, runtime: runtime),
      PrintJobType.kitchen => KitchenPrinter(device, runtime: runtime),
      PrintJobType.kitchenCancel => KitchenCancelPrinter(
        device,
        runtime: runtime,
      ),
      PrintJobType.weighTicket => WeighTicketPrinter(device, runtime: runtime),
      PrintJobType.fiscalDanfe => FiscalDanfePrinter(device, runtime: runtime),
      PrintJobType.printerTest => TestPrinter(device, runtime: runtime),
      PrintJobType.other => GenericPrinter(device, runtime: runtime),
    };
  }

  final PrinterDevice device;
  final PrinterRuntime runtime;

  /// O que esta impressora imprime — o mesmo valor gravado em `job_type`.
  PrintJobType get jobType;

  /// O trabalho pode esperar na fila local quando o equipamento não responde?
  ///
  /// Vale `false` só para o que perde o sentido depois: uma nota de teste que
  /// sai meia hora depois não diz mais nada sobre o equipamento.
  bool get queueable => true;

  PrinterEndpoint get target => device.endpoint;

  /// Monta um documento deste tipo, com o `job_type` já correto.
  PrintDocument compose({
    required String content,
    String? barcode,
    String? qr,
  }) => PrintDocument(
    type: jobType,
    content: content,
    barcode: barcode,
    qr: qr,
  );

  /// Entrega o documento ao equipamento.
  ///
  /// Lança [PrinterCommunicationException] em qualquer falha de comunicação —
  /// é o que a fila local usa para decidir entre repetir mais tarde e desistir.
  Future<void> send(PrintDocument document) =>
      _reserveInProcess(device.lockResource, () => _send(document));

  Future<void> _send(PrintDocument document) async {
    final startedAt = DateTime.now();
    final missing = device.missingConfiguration;
    if (missing != null) {
      // Configuração incompleta não é falha de comunicação: nenhuma repetição
      // resolve, e o aviso precisa dizer o que falta cadastrar.
      throw _publish(
        PrinterCommunicationException(
          message: 'Falha ao comunicar com ${device.label}. $missing',
          recommendedAction: 'Revise a configuração local da impressora.',
        ),
      );
    }

    final transport = PrinterTransport.forDevice(
      device,
      timing: runtime.timing,
      networkWriter: runtime.networkWriter,
    );

    // Reserva o equipamento antes de qualquer contato com ele. Vale para
    // TODOS os transportes, não só o serial: a Balança Rápida roda como
    // processo à parte (`ScaleWindowLauncher` usa `Process.start`) com o seu
    // próprio agente imprimindo, a fila local gira sozinha por tempo, e o
    // evento do WebSocket pode disparar outra rodada no mesmo instante. Sem
    // trava, dois envios simultâneos ao mesmo equipamento é exatamente o que
    // produz falha só na impressão automática: o teste manual, feito sozinho,
    // nunca disputa o equipamento com ninguém. Numa térmica de rede isso
    // aparece como "Connection timed out" na 9100 (ela aceita uma sessão por
    // vez); numa serial, como "Argumento inválido" em dois `tcsetattr` quase
    // simultâneos.
    //
    // `acquireQueued` espera em ordem de chegada — sem isso, um retry
    // otimista podia deixar quem pediu primeiro esperando mais que quem pediu
    // depois, só por sorte no instante de cada tentativa.
    final lock = await PeripheralLock.acquireQueued(
      device.lockResource,
      role: 'impressora',
      detail: jobType.wire,
      timeout: runtime.lockTimeout,
    );
    if (lock == null) {
      final owner = await PeripheralLock.currentOwner(device.lockResource);
      throw _publish(
        PrinterCommunicationException(
          message: owner == null
              ? '${device.label} está ocupada por outro processo.'
              : '${device.label} está em uso por ${owner.describe()}.',
          recommendedAction:
              'Aguarde a impressão em andamento terminar e tente novamente.',
        ),
      );
    }

    try {
      if (transport.needsAvailabilityCheck && !await probe()) {
        throw PrinterCommunicationException(
          message:
              'Não foi possível abrir ${device.label}: '
              'dispositivo não encontrado.',
          recommendedAction:
              'Confira o cabo, a energia e a porta configurada. O PDV '
              'continuará funcionando normalmente.',
        );
      }

      await transport.write(
        EscPosCodec.rawTransportBytes(
          document.content,
          isEscPos: target.isEscPos,
          barcodeValue: document.barcode,
          qrValue: document.qr,
        ),
      );
      _lastSuccessfulSend[device.lockResource] = DateTime.now();
      _publishStatus(PrinterAvailability.available);
      AppLogger.instance.info(
        'print_send_ok',
        data: {
          'printer': device.label,
          'job_type': jobType.wire,
          'ligacao': target.connection.name,
          'ms': DateTime.now().difference(startedAt).inMilliseconds,
        },
      );
    } on PrinterCommunicationException catch (error) {
      throw _publish(error);
    } catch (error) {
      throw _publish(
        PrinterCommunicationException(
          message: 'Falha ao comunicar com ${device.label}: $error',
          recommendedAction:
              'Confira o cabo, a energia e a porta configurada. O PDV '
              'continuará funcionando normalmente.',
        ),
      );
    } finally {
      await lock.release();
    }
  }

  /// O equipamento está ao alcance?
  ///
  /// Nunca abre um canal enquanto um trabalho está usando o equipamento: uma
  /// térmica de rede aceita uma sessão por vez, e um connect/close de
  /// verificação no meio de um cupom derruba justamente a impressão que
  /// estava saindo. Ocupada imprimindo é a melhor prova de que está viva.
  Future<bool> probe() async {
    final custom = runtime.availabilityProbe;
    if (custom != null) return custom(target);
    if (!device.isAddressable) return false;

    // Um trabalho desta janela já está com o equipamento: bater na porta
    // agora é justamente o que derruba a impressão em andamento.
    if (_inProcessTurn.containsKey(device.lockResource)) return true;

    final lastSuccess = _lastSuccessfulSend[device.lockResource];
    if (lastSuccess != null &&
        DateTime.now().difference(lastSuccess) < _recentSendWindow) {
      return true;
    }

    final lock = await PeripheralLock.tryAcquire(
      device.lockResource,
      role: 'impressora',
      detail: 'verificação',
    );
    if (lock == null) return true; // Ocupada com um cupom: está viva.
    try {
      return await _probeHardware();
    } catch (_) {
      return false;
    } finally {
      await lock.release();
    }
  }

  Future<bool> _probeHardware() async {
    switch (target.connection) {
      case PrinterConnection.serial:
        final configured = target.endpoint.trim();
        final detected = SerialPort.availablePorts.any(
          (port) => Platform.isWindows
              ? port.toLowerCase() == configured.toLowerCase()
              : port == configured,
        );
        return detected ||
            (!Platform.isWindows && await File(configured).exists());
      case PrinterConnection.network:
        final socket = await Socket.connect(
          target.host,
          target.port,
          timeout: target.timeout,
        );
        socket.destroy();
        return true;
      case PrinterConnection.spool:
        if (Platform.isWindows) {
          final safeName = target.endpoint.replaceAll("'", "''");
          final result = await Process.run('powershell.exe', [
            '-NoProfile',
            '-NonInteractive',
            '-Command',
            "Get-Printer -Name '$safeName' -ErrorAction Stop | Out-Null",
          ]).timeout(target.timeout);
          return result.exitCode == 0;
        }
        final result = await Process.run('lpstat', [
          '-p',
          target.endpoint,
        ]).timeout(target.timeout);
        return result.exitCode == 0;
    }
  }

  PrinterCommunicationException _publish(PrinterCommunicationException error) {
    _publishStatus(
      PrinterAvailability(
        PrinterAvailabilityPhase.unavailable,
        error.message,
      ),
    );
    AppLogger.instance.warning(
      'print_send_failed',
      data: {
        'printer': device.label,
        'job_type': jobType.wire,
        'motivo': error.message,
      },
    );
    return error;
  }

  void _publishStatus(PrinterAvailability status) =>
      runtime.onStatus?.call(status);

  /// Um envio bem-sucedido recente vale como prova de vida.
  ///
  /// A verificação periódica batia na porta de cada impressora a cada 15
  /// segundos, o dia inteiro. Numa térmica de rede isso é um connect/close
  /// seguido de RST na 9100, e algumas delas seguram a sessão anterior por
  /// alguns segundos depois disso — a impressão que caísse nessa janela
  /// falhava sem nenhum motivo aparente.
  static final Map<String, DateTime> _lastSuccessfulSend = {};

  static const _recentSendWindow = Duration(seconds: 60);

  /// Fila em memória, por equipamento, dentro desta janela.
  ///
  /// A reserva entre processos é um arquivo travado ([PeripheralLock]), e no
  /// Linux uma trava dessas **não** conflita com o próprio processo que já a
  /// detém: dois envios simultâneos daqui passariam os dois. E eles acontecem
  /// o tempo todo — o timer da fila, o evento do WebSocket e um cupom
  /// montado agora na tela chegam juntos. Esta fila garante a vez antes de
  /// chegar ao arquivo; a trava em disco continua respondendo pelas outras
  /// janelas (Balança Rápida) e pelo PDV vizinho.
  static final Map<String, Future<void>> _inProcessTurn = {};

  static Future<void> _reserveInProcess(
    String resource,
    Future<void> Function() action,
  ) {
    final previous = _inProcessTurn[resource];
    final completer = Completer<void>();
    _inProcessTurn[resource] = completer.future;

    Future<void> run() async {
      try {
        await action();
      } finally {
        completer.complete();
        if (identical(_inProcessTurn[resource], completer.future)) {
          _inProcessTurn.remove(resource);
        }
      }
    }

    return previous == null ? run() : previous.then((_) => run());
  }
}

/// Recibo de venda / cupom do cliente.
class ReceiptPrinter extends Printer {
  ReceiptPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.receipt;
}

/// Comanda de produção (cozinha, bar, chapa).
class KitchenPrinter extends Printer {
  KitchenPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.kitchen;
}

/// Aviso de cancelamento de item já enviado à produção.
class KitchenCancelPrinter extends Printer {
  KitchenCancelPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.kitchenCancel;
}

/// Nota de pesagem da balança.
class WeighTicketPrinter extends Printer {
  WeighTicketPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.weighTicket;
}

/// DANFE NFC-e (o único com QR Code).
class FiscalDanfePrinter extends Printer {
  FiscalDanfePrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.fiscalDanfe;
}

/// Nota de teste do cadastro de impressoras.
class TestPrinter extends Printer {
  TestPrinter(super.device, {super.runtime});

  @override
  PrintJobType get jobType => PrintJobType.printerTest;

  /// Um teste que sai meia hora depois não diz nada sobre o equipamento:
  /// quem clicou "testar" está olhando a impressora agora.
  @override
  bool get queueable => false;
}

/// Tipo de cupom que este PDV ainda não conhece.
class GenericPrinter extends Printer {
  GenericPrinter(super.device, {super.runtime, PrintJobType? type})
    : _type = type ?? PrintJobType.other;

  final PrintJobType _type;

  @override
  PrintJobType get jobType => _type;
}
