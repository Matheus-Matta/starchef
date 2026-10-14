import 'dart:async';
import 'dart:isolate';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/core/hardware/leitor_serial_isolado.dart';

/// A Balança Rápida caía no Linux ao pegar o peso.
///
/// A leitura da porta roda num isolate preso num laço de chamadas nativas. A
/// `SerialPortReader` da biblioteca o "matava" com `Isolate.kill()` no modo
/// padrão (`beforeNextEvent`), que só age quando o isolate volta ao laço de
/// eventos — e ele nunca volta. O isolate seguia lendo a porta depois de ela
/// ser fechada e liberada: no Linux o descritor é reaproveitado pela porta
/// reaberta, a leitura nunca falha, e o acesso à memória liberada derruba o
/// processo inteiro.
///
/// Estes laços falsos fazem o mesmo que o nativo: nunca voltam ao laço de
/// eventos.
void lacoQueNuncaVolta(List<Object?> args) {
  final saida = args[0]! as SendPort;
  saida.send(Uint8List.fromList([49, 46, 48, 13, 10]));
  var n = 0;
  while (true) {
    n++;
    if (n == -1) break;
  }
}

void lacoQueFalha(List<Object?> args) {
  final saida = args[0]! as SendPort;
  saida.send('cabo solto');
}

void main() {
  test('o kill padrao NAO para um laco que nunca volta (o defeito)', () async {
    final saiu = ReceivePort();
    final isolate = await Isolate.spawn(lacoQueNuncaVolta, <Object?>[
      ReceivePort().sendPort,
    ], onExit: saiu.sendPort);
    isolate.kill(); // o que a biblioteca fazia
    final terminou = await saiu.first
        .then((_) => true)
        .timeout(const Duration(seconds: 1), onTimeout: () => false);
    isolate.kill(priority: Isolate.immediate);
    saiu.close();

    expect(terminou, isFalse);
  });

  test('parar mata o leitor e so entao libera a porta', () async {
    var liberada = false;
    final leitor = LeitorSerialIsolado(
      endereco: 0,
      entrada: lacoQueNuncaVolta,
      liberarPorta: () => liberada = true,
    );
    final dados = <List<int>>[];
    leitor.dados.listen(dados.add);
    await leitor.iniciar();
    await Future<void>.delayed(const Duration(milliseconds: 50));

    final saiu = await leitor.parar();

    expect(saiu, isTrue);
    expect(liberada, isTrue);
    expect(dados.single, [49, 46, 48, 13, 10]);
  });

  test('parar antes de iniciar terminar nao deixa o isolate solto', () async {
    var liberada = false;
    final leitor = LeitorSerialIsolado(
      endereco: 0,
      entrada: lacoQueNuncaVolta,
      liberarPorta: () => liberada = true,
    );
    leitor.dados.listen((_) {});
    final iniciando = leitor.iniciar();

    final saiu = await leitor.parar();
    await iniciando;

    expect(saiu, isTrue);
    expect(liberada, isTrue);
  });

  test('a falha da porta chega como erro e o leitor termina sozinho', () async {
    var liberada = false;
    final leitor = LeitorSerialIsolado(
      endereco: 0,
      entrada: lacoQueFalha,
      liberarPorta: () => liberada = true,
    );
    final erro = Completer<Object>();
    leitor.dados.listen((_) {}, onError: erro.complete);
    await leitor.iniciar();

    expect(await erro.future, contains('cabo solto'));
    expect(await leitor.parar(), isTrue);
    expect(liberada, isTrue);
  });

  test('parar duas vezes libera a porta uma vez so', () async {
    var liberacoes = 0;
    final leitor = LeitorSerialIsolado(
      endereco: 0,
      entrada: lacoQueNuncaVolta,
      liberarPorta: () => liberacoes++,
    );
    leitor.dados.listen((_) {});
    await leitor.iniciar();

    await Future.wait([leitor.parar(), leitor.parar()]);

    expect(liberacoes, 1);
  });
}
