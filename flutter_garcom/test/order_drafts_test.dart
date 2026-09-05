import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/features/orders/data/order_drafts.dart';

/// Os itens escolhidos e ainda não enviados.
///
/// O lançamento deixou de sair do aparelho item a item: cada toque virava uma
/// ida à rede que podia falhar sozinha, e o garçom só descobria muito depois,
/// numa pendência que já não dizia de que item se tratava. Agora eles se
/// acumulam aqui e vão juntos, quando ele confirma — e por isso precisam
/// sobreviver a fechar o app tanto quanto a fila de pendências.
void main() {
  late Directory tempDir;
  late OrderDrafts drafts;

  DraftItem item({String orderId = 'pedido-1', String name = 'Coxinha'}) =>
      DraftItem(
        id: OrderDrafts.newId(),
        orderId: orderId,
        productId: 'produto-1',
        productName: name,
        quantity: 2,
        addonIds: const [],
        note: '',
      );

  setUp(() async {
    tempDir = Directory.systemTemp.createTempSync('starchef-garcom-drafts-');
    drafts = OrderDrafts(
      testFile: File('${tempDir.path}${Platform.pathSeparator}rascunho.json'),
    );
    await drafts.restore();
  });

  tearDown(() {
    drafts.dispose();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  test('o item escolhido fica esperando, separado por pedido', () async {
    await drafts.add(item());
    await drafts.add(item(name: 'Refrigerante'));
    await drafts.add(item(orderId: 'pedido-2'));

    expect(drafts.countFor('pedido-1'), 2);
    expect(drafts.countFor('pedido-2'), 1);
    expect(drafts.forOrder('pedido-1').first.label, '2x Coxinha');
  });

  test('sobrevive a fechar e abrir o app', () async {
    await drafts.add(item());

    // Uma instância nova sobre o mesmo arquivo simula reabrir o app.
    final reaberto = OrderDrafts(testFile: drafts.testFile);
    await reaberto.restore();

    expect(reaberto.countFor('pedido-1'), 1);
    reaberto.dispose();
  });

  test('enviado ou removido, some da lista e do disco', () async {
    final escolhido = await drafts.add(item());
    await drafts.add(item(name: 'Guaraná'));

    await drafts.remove(escolhido.id);
    expect(drafts.countFor('pedido-1'), 1);

    await drafts.clearOrder('pedido-1');
    final reaberto = OrderDrafts(testFile: drafts.testFile);
    await reaberto.restore();
    expect(reaberto.isEmpty, isTrue);
    reaberto.dispose();
  });

  test(
    'o pedido criado offline leva os itens junto ao ganhar o id real',
    () async {
      // Sem isto, os itens escolhidos antes de a criação sincronizar ficariam
      // apontando para um id que deixou de existir — e nunca seriam enviados.
      await drafts.add(item(orderId: 'offline-abc'));

      await drafts.reassign('offline-abc', 'pedido-real-1');

      expect(drafts.countFor('offline-abc'), 0);
      expect(drafts.countFor('pedido-real-1'), 1);
    },
  );

  test('avisa a tela a cada mudança', () async {
    var avisos = 0;
    drafts.addListener(() => avisos++);

    final escolhido = await drafts.add(item());
    await drafts.remove(escolhido.id);

    expect(avisos, 2);
  });
}
