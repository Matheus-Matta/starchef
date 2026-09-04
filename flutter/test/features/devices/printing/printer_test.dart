import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/hardware/peripheral_lock.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';
import 'package:starchef_pdv/features/devices/printing/print_document.dart';
import 'package:starchef_pdv/features/devices/printing/printer.dart';
import 'package:starchef_pdv/features/devices/printing/printer_device.dart';
import 'package:starchef_pdv/features/devices/printing/printer_transport.dart';

void main() {
  /// Cada teste isola os arquivos de trava num diretório próprio: a reserva
  /// do equipamento é um arquivo em disco, compartilhado entre processos.
  void useTemporaryLockDirectory() {
    late Directory directory;
    setUp(() async {
      directory = await Directory.systemTemp.createTemp('starchef-printer');
      AppPaths.overrideDataDirectory(directory);
    });
    tearDown(() async {
      AppPaths.overrideDataDirectory(null);
      try {
        if (await directory.exists()) await directory.delete(recursive: true);
      } on FileSystemException {
        // O Windows ainda pode estar com o arquivo de trava aberto; limpar o
        // temporário é conveniência, não parte do que está sendo testado.
      }
    });
  }

  PrinterDevice device(Map<String, dynamic> json) =>
      PrinterDevice.fromJson(json);

  group('Printer envio', () {
    useTemporaryLockDirectory();

    test('impressão IP não abre uma conexão de teste antes do envio', () async {
      var probes = 0;
      var writes = 0;
      final printer = KitchenPrinter(
        device({
          'connection_type': 'network',
          'host': '192.0.2.10',
          'port': 9100,
          'driver_type': 'escpos',
        }),
        runtime: PrinterRuntime(
          availabilityProbe: (_) async {
            probes++;
            return false;
          },
          networkWriter: (target, bytes) async {
            writes++;
            expect(target.host, '192.0.2.10');
            expect(target.port, 9100);
            expect(bytes, isNotEmpty);
          },
          timing: PrintTiming(delay: (_) async {}),
        ),
      );

      await printer.send(printer.compose(content: 'COMANDA 42'));

      // Em TCP/IP o próprio envio é a prova de disponibilidade: um
      // connect/close de teste seguido de reconexão imediata faz algumas
      // térmicas aceitarem a primeira sessão e ignorarem a segunda.
      expect(probes, 0);
      expect(writes, 1);
    });

    test('publica disponível no status depois de imprimir', () async {
      final published = <PrinterAvailability>[];
      final printer = ReceiptPrinter(
        device({
          'connection_type': 'network',
          'host': '192.0.2.10',
          'port': 9100,
        }),
        runtime: PrinterRuntime(
          networkWriter: (_, _) async {},
          onStatus: published.add,
          timing: PrintTiming(delay: (_) async {}),
        ),
      );

      await printer.send(printer.compose(content: 'RECIBO'));

      expect(published.last.isAvailable, isTrue);
    });

    test('impressora sem endereço não vira falha de comunicação vaga', () async {
      final printer = ReceiptPrinter(
        device({'name': 'Cozinha', 'connection_type': 'network'}),
      );

      await expectLater(
        printer.send(printer.compose(content: 'RECIBO')),
        throwsA(
          isA<PrinterCommunicationException>().having(
            (error) => error.message,
            'message',
            allOf(contains('Cozinha'), contains('endereço IP')),
          ),
        ),
      );
    });

    test('impressora ausente gera aviso amigável sem exceção nativa', () async {
      final printer = KitchenPrinter(
        device({
          'name': 'Cozinha',
          'connection_type': 'serial',
          'endpoint': 'COM99',
        }),
        runtime: PrinterRuntime(availabilityProbe: (_) async => false),
      );

      await expectLater(
        printer.send(printer.compose(content: 'COMANDA')),
        throwsA(
          isA<PrinterCommunicationException>().having(
            (error) => error.message,
            'message',
            // O aviso precisa dizer QUAL impressora falhou: o terminal tem
            // mais de uma, e "impressora desconectada" sozinho não ajuda.
            allOf(contains('Cozinha'), contains('COM99')),
          ),
        ),
      );
    });

    test(
      'porta serial presa por outro processo dá erro claro, sem tentar abrir',
      () async {
        // Reproduz a Balança Rápida (processo à parte) segurando a mesma
        // porta que a impressão automática do PDV principal tenta usar. Sem
        // a trava, os dois processos disputavam `tcsetattr` na mesma porta e
        // o sintoma era "Argumento inválido" — só na automática, nunca no
        // teste manual isolado.
        final held = await PeripheralLock.tryAcquire(
          'printer:/dev/ttyACM0',
          role: 'balanca-rapida',
        );
        addTearDown(() => held?.release());
        expect(held, isNotNull);

        final printer = KitchenPrinter(
          device({
            'id': 'printer-1',
            'connection_type': 'serial',
            'endpoint': '/dev/ttyACM0',
          }),
          runtime: const PrinterRuntime(
            lockTimeout: Duration(milliseconds: 200),
          ),
        );

        await expectLater(
          printer.send(printer.compose(content: 'COMANDA')),
          throwsA(
            isA<PrinterCommunicationException>().having(
              (error) => error.message,
              'message',
              contains('em uso'),
            ),
          ),
        );
      },
      timeout: const Timeout(Duration(seconds: 10)),
    );

    test(
      'dois cupons para a mesma impressora de rede não saem ao mesmo tempo',
      () async {
        // É o erro que só aparecia na impressão automática: a fila local, o
        // evento do WebSocket e a janela da Balança mandam papel para a
        // mesma térmica em rajada, e ela aceita UMA sessão por vez na 9100 —
        // a segunda conexão ficava sem resposta até estourar o tempo limite
        // ("Connection timed out"). O recibo de venda, clicado sozinho,
        // nunca disputava com ninguém e por isso nunca falhava.
        var concurrent = 0;
        var maxConcurrent = 0;
        PrinterRuntime runtime() => PrinterRuntime(
          networkWriter: (_, _) async {
            concurrent++;
            maxConcurrent = maxConcurrent > concurrent
                ? maxConcurrent
                : concurrent;
            await Future<void>.delayed(const Duration(milliseconds: 40));
            concurrent--;
          },
          timing: PrintTiming(delay: (_) async {}),
        );
        final json = {
          'connection_type': 'network',
          'host': '192.0.2.11',
          'port': 9100,
          'driver_type': 'escpos',
        };
        final first = KitchenPrinter(device(json), runtime: runtime());
        final second = KitchenCancelPrinter(device(json), runtime: runtime());

        await Future.wait([
          first.send(first.compose(content: 'COMANDA 1')),
          second.send(second.compose(content: 'CANCELAMENTO')),
        ]);

        expect(maxConcurrent, 1);
      },
      timeout: const Timeout(Duration(seconds: 10)),
    );
  });

  group('Printer verificação de presença', () {
    useTemporaryLockDirectory();

    test('não sonda o equipamento enquanto ele está imprimindo', () async {
      // A verificação periódica batia na porta a cada 15 segundos. Numa
      // térmica de rede é um connect/close com RST na 9100, e cair no meio de
      // um cupom derrubava justamente a impressão que estava saindo.
      final json = {
        'connection_type': 'network',
        'host': '192.0.2.12',
        'port': 9100,
      };
      final held = await PeripheralLock.tryAcquire(
        PrinterDevice.fromJson(json).lockResource,
        role: 'impressora',
      );
      addTearDown(() => held?.release());

      expect(await GenericPrinter(device(json)).probe(), isTrue);
    });

    test('um envio recente vale como prova de vida', () async {
      final json = {
        'connection_type': 'network',
        'host': '192.0.2.13',
        'port': 9100,
      };
      final printer = ReceiptPrinter(
        device(json),
        runtime: PrinterRuntime(
          networkWriter: (_, _) async {},
          timing: PrintTiming(delay: (_) async {}),
        ),
      );
      await printer.send(printer.compose(content: 'RECIBO'));

      // Sem sonda alternativa: se a janela do envio recente não valesse,
      // isto tentaria abrir um socket para um IP inexistente e falharia.
      expect(await GenericPrinter(device(json)).probe(), isTrue);
    });
  });

  group('Printer por tipo de documento', () {
    test('a fila local reconstrói a impressora do tipo gravado', () {
      const json = {'connection_type': 'network', 'host': '192.0.2.10'};
      Printer forType(PrintJobType type) => Printer.forDocument(
        json,
        PrintDocument(type: type, content: 'X'),
      );

      expect(forType(PrintJobType.receipt), isA<ReceiptPrinter>());
      expect(forType(PrintJobType.kitchen), isA<KitchenPrinter>());
      expect(forType(PrintJobType.kitchenCancel), isA<KitchenCancelPrinter>());
      expect(forType(PrintJobType.weighTicket), isA<WeighTicketPrinter>());
      expect(forType(PrintJobType.fiscalDanfe), isA<FiscalDanfePrinter>());
      expect(forType(PrintJobType.printerTest), isA<TestPrinter>());
    });

    test('a nota de teste não espera na fila', () {
      const json = {'connection_type': 'network', 'host': '192.0.2.10'};
      // Um teste que sai meia hora depois não diz mais nada sobre o
      // equipamento: quem clicou está olhando a impressora agora.
      expect(TestPrinter(PrinterDevice.fromJson(json)).queueable, isFalse);
      expect(KitchenPrinter(PrinterDevice.fromJson(json)).queueable, isTrue);
    });
  });
}
