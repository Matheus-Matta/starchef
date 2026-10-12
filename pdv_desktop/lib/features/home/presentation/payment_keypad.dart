import 'package:flutter/material.dart';

/// O teclado numérico da tela de pagamento, ocupando a altura que sobrar.
///
/// Era uma grade de proporção fixa. Com taxa, CPF/CNPJ e desconto logo abaixo
/// dele, a grade era CORTADA nas telas menores; agora cada linha divide o
/// espaço que há, e as teclas encolhem em vez de sumir.
class PaymentKeypad extends StatelessWidget {
  const PaymentKeypad({super.key, required this.onKey});

  /// '0'–'9', 'clear' (C) ou 'back' (apagar).
  final ValueChanged<String> onKey;

  static const _teclas = [
    ['1', '2', '3'],
    ['4', '5', '6'],
    ['7', '8', '9'],
    ['clear', '0', 'back'],
  ];

  @override
  Widget build(BuildContext context) => Column(
    spacing: 6,
    children: [
      for (final linha in _teclas)
        Expanded(
          child: Row(
            spacing: 6,
            children: [
              for (final tecla in linha)
                Expanded(
                  child: SizedBox.expand(
                    child: OutlinedButton(
                      key: Key('payment-key-$tecla'),
                      onPressed: () => onKey(tecla),
                      child: switch (tecla) {
                        'back' => const Icon(Icons.backspace_outlined),
                        'clear' => const Text('C'),
                        _ => Text(
                          tecla,
                          style: const TextStyle(
                            fontSize: 17,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      },
                    ),
                  ),
                ),
            ],
          ),
        ),
    ],
  );
}
