import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/logging/app_logger.dart';
import 'package:starchef_pdv/core/storage/app_paths.dart';

/// O log vai para o disco em texto puro — o que estiver nele pode ser lido por
/// qualquer um com acesso à máquina. A máscara é a única barreira, e ela
/// precisa alcançar segredo em QUALQUER profundidade: este PDV registra corpo
/// de requisição inteiro em vários pontos.
void main() {
  late Directory directory;

  // Um diretório para o arquivo inteiro: o `AppLogger` é um singleton que
  // guarda o `File` resolvido na primeira escrita, então trocar de pasta entre
  // os testes faria os seguintes escreverem no caminho já apagado.
  setUpAll(() async {
    directory = await Directory.systemTemp.createTemp('starchef-log-');
    AppPaths.overrideDataDirectory(directory);
  });

  tearDownAll(() async {
    AppPaths.overrideDataDirectory(null);
    if (directory.existsSync()) await directory.delete(recursive: true);
  });

  Future<String> loggedLines() async {
    await AppLogger.instance.flush();
    return AppPaths.dataFile('pdv.log').readAsString();
  }

  test('segredo aninhado em mapa não chega ao disco', () async {
    AppLogger.instance.info(
      'teste_mascara',
      data: {
        'origin': {'actor': 'joao', 'access_token': 'super-secreto'},
        'pedido': 'abc',
      },
    );

    final log = await loggedLines();

    expect(log, contains('joao'));
    expect(log, contains('abc'));
    expect(log, isNot(contains('super-secreto')));
    expect(log, contains('***'));
  });

  test('segredo dentro de lista de operações não chega ao disco', () async {
    AppLogger.instance.info(
      'teste_mascara_lista',
      data: {
        'fila': [
          {'path': '/orders/', 'refresh_token': 'token-da-fila'},
        ],
      },
    );

    final log = await loggedLines();

    expect(log, contains('/orders/'));
    expect(log, isNot(contains('token-da-fila')));
  });

  test('valor comum continua legível', () async {
    AppLogger.instance.info(
      'teste_sem_segredo',
      data: {'impressora': 'IMP CX 1', 'tentativa': 2},
    );

    final log = await loggedLines();

    // Mascarar demais também é defeito: o log existe para diagnosticar.
    expect(log, contains('"impressora":"IMP CX 1"'));
    expect(log, contains('"tentativa":2'));
  });
}
