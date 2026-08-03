import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/widgets/touch_keypad.dart';

Widget _boxed(double width) => MaterialApp(
  home: Scaffold(
    body: SizedBox(width: width, child: TouchKeypad(onKey: (_) {})),
  ),
);

void main() {
  group('widget', () {
    testWidgets('todas as teclas usam o mesmo estilo (OutlinedButton)', (
      tester,
    ) async {
      await tester.pumpWidget(_boxed(400));

      // 12 teclas: 0-9, C e apagar — nenhuma delas deve ser FilledButton,
      // que era o estilo antigo dos dígitos, diferente de C/apagar.
      expect(find.byType(OutlinedButton), findsNWidgets(12));
      expect(find.byType(FilledButton), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('numa coluna estreita, os botões encolhem sem estourar', (
      tester,
    ) async {
      await tester.pumpWidget(_boxed(180));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('numa coluna larga, os botões crescem até o teto', (
      tester,
    ) async {
      await tester.pumpWidget(_boxed(900));
      await tester.pumpAndSettle();

      final button = tester.getSize(find.byType(OutlinedButton).first);
      // Teto de 64px (TouchKeypad._maxButtonSize): mesmo com muito espaço
      // sobrando, o botão não vira gigante.
      expect(button.height, lessThanOrEqualTo(64));
      expect(tester.takeException(), isNull);
    });

  });

  test('acumula dígitos até o limite configurado', () {
    var value = '';
    for (final key in ['1', '2', '3']) {
      value = nextKeypadValue(value, key, maximumLength: 3);
    }

    expect(value, '123');
    expect(nextKeypadValue(value, '4', maximumLength: 3), '123');
  });

  test('backspace remove um dígito e não quebra em texto vazio', () {
    expect(nextKeypadValue('120', 'backspace'), '12');
    expect(nextKeypadValue('', 'backspace'), '');
  });

  test('a tecla C limpa tudo', () {
    expect(nextKeypadValue('98765', 'C'), '');
  });

  group('entrada decimal', () {
    test('a vírgula abre casas decimais e prefixa zero', () {
      expect(nextKeypadValue('', ',', allowDecimal: true), '0,');
      expect(nextKeypadValue('1', ',', allowDecimal: true), '1,');
    });

    test('uma segunda vírgula é ignorada', () {
      expect(nextKeypadValue('1,5', ',', allowDecimal: true), '1,5');
    });

    test('a vírgula não entra quando decimais não são permitidos', () {
      expect(nextKeypadValue('12', ','), '12');
    });

    test('limita as casas decimais à precisão da balança', () {
      var value = '1,';
      for (final key in ['2', '5', '0', '9']) {
        value = nextKeypadValue(value, key, allowDecimal: true);
      }

      expect(value, '1,250');
    });
  });
}
