import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv_desktop/features/commands/presentation/command_card.dart';

/// O cartão precisa MOSTRAR o que o operador procura.
///
/// Um cartão desenhado e vazio é pior que cartão nenhum: a tela parece
/// carregada, e a pessoa fica procurando o número que nunca vai aparecer. Foi
/// exatamente o que aconteceu quando a faixa de estado à esquerda usava uma
/// borda não uniforme com canto arredondado — ilegal no Flutter, e descoberto
/// só na hora de PINTAR, o que apaga os filhos sem erro de compilação.
Widget _tela(Map<String, dynamic> comanda, {ThemeData? tema}) => MaterialApp(
  theme: tema,
  home: Scaffold(
    body: CommandCard(comanda: comanda, ativo: false, onTap: () {}),
  ),
);

const _comanda = {
  'id': 'c3',
  'number': 3,
  'code': '0003',
  'pending_items': 2,
  'customer_name': 'Ana',
};

void main() {
  testWidgets('o cartao mostra numero, codigo, cliente e estado', (
    tester,
  ) async {
    await tester.pumpWidget(_tela(_comanda));

    expect(find.text('3'), findsOneWidget);
    expect(find.text('0003'), findsOneWidget);
    expect(find.text('Ana'), findsOneWidget);
    expect(find.text('OCUPADA'), findsOneWidget);
  });

  testWidgets('comanda sem nada pendente aparece como livre', (tester) async {
    // "Em uso" é ter anotação pendente, e não um campo de estado: o cartão é
    // um bloco de notas, e o que decide é ter o que cobrar.
    await tester.pumpWidget(
      _tela(const {
        'id': 'c9',
        'number': 9,
        'code': '0009',
        'pending_items': 0,
      }),
    );

    expect(find.text('9'), findsOneWidget);
    expect(find.text('LIVRE'), findsOneWidget);
    expect(find.text('—'), findsOneWidget);
  });

  testWidgets('no tema escuro o texto do cartao continua legivel', (
    tester,
  ) async {
    // O cartão pinta o próprio fundo com `surface` mas deixa a cor do texto
    // para o tema. Num tema em que o texto não acompanha, o resultado é escuro
    // sobre escuro: o cartão aparece desenhado e VAZIO.
    await tester.pumpWidget(
      _tela(_comanda, tema: ThemeData(brightness: Brightness.dark)),
    );

    final numero = tester.widget<Text>(find.text('3'));
    final corDoNumero =
        numero.style?.color ??
        DefaultTextStyle.of(tester.element(find.text('3'))).style.color;
    final fundo = ThemeData(brightness: Brightness.dark).colorScheme.surface;

    expect(corDoNumero, isNotNull);
    expect(
      corDoNumero!.toARGB32(),
      isNot(fundo.toARGB32()),
      reason: 'texto da mesma cor do fundo é um cartão vazio na prática',
    );
  });
}
