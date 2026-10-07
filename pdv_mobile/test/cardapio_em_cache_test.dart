import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_mobile/core/network/read_cache.dart';

/// O cardápio abre na hora com a última cópia, como no PDV desktop.
///
/// Toda vez que o garçom abria "Adicionar item" o app baixava o cardápio de
/// novo, com o cliente esperando. Agora a cópia recente aparece na hora e,
/// passado o prazo curto, é relida POR TRÁS para a próxima abertura.
void main() {
  late DateTime agora;
  late int leituras;
  late String nome;

  ReadCache cache() {
    agora = DateTime(2026, 10, 7, 12);
    leituras = 0;
    nome = 'X-Burger';
    return ReadCache(clock: () => agora);
  }

  Future<Map<String, dynamic>> servidor() async {
    leituras++;
    return {
      'results': [
        {'name': nome},
      ],
    };
  }

  Future<void> rodarPorTras() => Future<void>.delayed(Duration.zero);

  test('a segunda abertura não vai ao servidor', () async {
    final c = cache();
    await c.read('u1|/menu/products/?p=1', servidor);
    final segunda = await c.read('u1|/menu/products/?p=1', servidor);

    expect(leituras, 1);
    expect((segunda['results'] as List).single['name'], 'X-Burger');
  });

  test('cópia velha aparece na hora e é relida por trás', () async {
    final c = cache();
    await c.read('k', servidor);
    nome = 'X-Salada';
    agora = agora.add(const Duration(minutes: 1));

    final mostrada = await c.read('k', servidor);
    await rodarPorTras();

    expect((mostrada['results'] as List).single['name'], 'X-Burger');
    expect(leituras, 2);
    final depois = await c.read('k', servidor);
    expect((depois['results'] as List).single['name'], 'X-Salada');
  });

  test(
    'passado o limite, espera o servidor em vez de mostrar dado muito velho',
    () async {
      final c = cache();
      await c.read('k', servidor);
      nome = 'X-Salada';
      agora = agora.add(const Duration(hours: 1));

      final lida = await c.read('k', servidor);

      expect((lida['results'] as List).single['name'], 'X-Salada');
    },
  );

  test('chave diferente (outra busca, outro usuário) não aproveita', () async {
    final c = cache();
    await c.read('u1|k', servidor);
    await c.read('u2|k', servidor);
    expect(leituras, 2);
  });

  test(
    'falha da releitura por trás mantém a cópia e não derruba a tela',
    () async {
      final c = cache();
      await c.read('k', servidor);
      agora = agora.add(const Duration(minutes: 1));

      final lida = await c.read('k', () async => throw Exception('sem rede'));
      await rodarPorTras();

      expect((lida['results'] as List).single['name'], 'X-Burger');
    },
  );

  test('limpar esquece tudo (troca de usuário)', () async {
    final c = cache()..clear();
    await c.read('k', servidor);
    c.clear();
    await c.read('k', servidor);
    expect(leituras, 2);
  });
}
