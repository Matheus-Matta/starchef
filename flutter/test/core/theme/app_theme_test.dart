import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_pdv/core/theme/app_theme.dart';

void main() {
  testWidgets('inputs e selects usam a mesma altura compacta dos botoes', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: AppTheme.light(),
        home: Scaffold(
          body: Center(
            child: SizedBox(
              width: 240,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const TextField(
                    decoration: InputDecoration(
                      hintText: 'Buscar',
                      prefixIcon: Icon(Icons.search),
                    ),
                  ),
                  const SizedBox(height: 8),
                  DropdownButtonFormField<String>(
                    initialValue: 'pending',
                    isExpanded: true,
                    decoration: const InputDecoration(labelText: 'Situacao'),
                    items: const [
                      DropdownMenuItem(
                        value: 'pending',
                        child: Text('Pendentes'),
                      ),
                    ],
                    onChanged: (_) {},
                  ),
                  const SizedBox(height: 8),
                  OutlinedButton(
                    onPressed: () {},
                    child: const Text('Periodo'),
                  ),
                  const SizedBox(height: 8),
                  // Os três tipos de botão entram porque cada um tem seu
                  // próprio tema: já aconteceu de um deles ficar dois pixels
                  // mais alto que os vizinhos sem ninguém notar.
                  ElevatedButton(onPressed: () {}, child: const Text('Salvar')),
                  const SizedBox(height: 8),
                  FilledButton(onPressed: () {}, child: const Text('Pagar')),
                  const SizedBox(height: 8),
                  TextButton(onPressed: () {}, child: const Text('Cancelar')),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    expect(
      tester.getSize(find.byType(TextField)).height,
      AppTheme.controlHeight,
    );
    expect(
      tester.getSize(find.byType(DropdownButtonFormField<String>)).height,
      AppTheme.controlHeight,
    );
    for (final botao in [
      find.byType(OutlinedButton),
      find.byType(ElevatedButton),
      find.byType(FilledButton),
      find.byType(TextButton),
    ]) {
      expect(
        tester.getSize(botao).height,
        AppTheme.controlHeight,
        reason: 'todo botão mede o mesmo que um campo ao lado',
      );
    }
    expect(tester.takeException(), isNull);
  });
}
