import 'package:flutter/material.dart';

/// Teclado numérico para operação por toque, sem depender do teclado físico.
///
/// O tamanho do botão vem do espaço disponível, não de um valor fixo: numa
/// coluna estreita (janela pequena, painel dividido) os botões encolhem
/// junto; numa coluna larga, crescem — sempre um pouco abaixo de um
/// quadrado, com folga para o dedo. Todas as teclas usam o mesmo estilo
/// (`OutlinedButton`), incluindo apagar e limpar, em vez de misturar
/// preenchido com contornado.
class TouchKeypad extends StatelessWidget {
  const TouchKeypad({super.key, required this.onKey, this.allowDecimal = false});

  /// Recebe `'0'`–`'9'`, `','`, `'C'` ou `'backspace'`.
  final ValueChanged<String> onKey;

  /// Substitui a tecla de limpar por vírgula, para entrada de peso e valores.
  final bool allowDecimal;

  static const _minButtonSize = 40.0;
  static const _maxButtonSize = 64.0;
  static const _spacing = 8.0;

  @override
  Widget build(BuildContext context) {
    final keys = [
      '1',
      '2',
      '3',
      '4',
      '5',
      '6',
      '7',
      '8',
      '9',
      allowDecimal ? ',' : 'C',
      '0',
      'backspace',
    ];
    return LayoutBuilder(
      builder: (context, constraints) {
        // Sem largura definida (ex.: dentro de uma Column com
        // mainAxisSize.min sem SizedBox), cai no teto — o mesmo resultado de
        // antes, quando o tamanho era fixo.
        final availableWidth = constraints.hasBoundedWidth
            ? constraints.maxWidth
            : _maxButtonSize * 3 + _spacing * 2;
        final buttonSize = ((availableWidth - _spacing * 2) / 3).clamp(
          _minButtonSize,
          _maxButtonSize,
        );
        final fontSize = (buttonSize * 0.38).clamp(14.0, 22.0);

        return SizedBox(
          height: buttonSize * 4 + _spacing * 3,
          child: GridView.builder(
            physics: const NeverScrollableScrollPhysics(),
            gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
              crossAxisCount: 3,
              mainAxisExtent: buttonSize,
              mainAxisSpacing: _spacing,
              crossAxisSpacing: _spacing,
            ),
            itemCount: keys.length,
            itemBuilder: (context, index) {
              final keyValue = keys[index];
              if (keyValue == 'backspace') {
                return OutlinedButton(
                  onPressed: () => onKey(keyValue),
                  child: Icon(Icons.backspace_outlined, size: fontSize + 2),
                );
              }
              return OutlinedButton(
                onPressed: () => onKey(keyValue),
                child: Text(
                  keyValue,
                  style: TextStyle(
                    fontSize: fontSize,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              );
            },
          ),
        );
      },
    );
  }
}

/// Aplica uma tecla do [TouchKeypad] ao texto atual.
///
/// Mantida separada do widget para poder ser testada sem construir a árvore e
/// para que quem guarda o texto (controller, estado, máquina) decida onde ele
/// vive.
String nextKeypadValue(
  String current,
  String key, {
  bool allowDecimal = false,
  int maximumLength = 32,
  int maximumDecimals = 3,
}) {
  if (key == 'C') return '';
  if (key == 'backspace') {
    return current.isEmpty ? current : current.substring(0, current.length - 1);
  }
  if (key == ',') {
    if (!allowDecimal || current.contains(',') || current.contains('.')) {
      return current;
    }
    return current.isEmpty ? '0,' : '$current,';
  }
  if (current.length >= maximumLength) return current;
  if (allowDecimal && current.contains(',')) {
    final decimals = current.length - current.indexOf(',') - 1;
    if (decimals >= maximumDecimals) return current;
  }
  return '$current$key';
}
