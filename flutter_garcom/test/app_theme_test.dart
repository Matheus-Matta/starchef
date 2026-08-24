import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:starchef_garcom/core/theme/app_theme.dart';

/// O `ColorScheme.fromSeed` do Material 3 deriva TODAS as superfícies (as que
/// PopupMenu, BottomSheet e Dialog leem) do matiz da cor semente — com
/// `primary` laranja, isso pintava esses fundos de um laranja-acinzentado em
/// vez de neutro. Este arquivo trava que:
///
/// 1. As superfícies usadas por menu/dropdown/bottom sheet/dialog são cinza
///    neutro (mesma escala zinc do cartão shadcn), não uma variação de laranja;
/// 2. `surfaceTint` está desligado, para nenhum componente elevado ganhar uma
///    lavagem de cor por conta própria;
/// 3. `primary` continua laranja — a marca não sumiu, só parou de vazar para
///    onde não devia.
void main() {
  /// Quão "sem cor" um tom é: 0 = cinza puro, valores maiores = mais matiz.
  /// Comparamos contra o próprio laranja da marca para garantir uma distância
  /// clara, em vez de cravar um número mágico de tolerância.
  double saturation(Color color) {
    final hsl = HSLColor.fromColor(color);
    return hsl.saturation;
  }

  for (final entry in {
    'light': AppTheme.materialLight(),
    'dark': AppTheme.materialDark(),
  }.entries) {
    final tema = entry.value;
    final scheme = tema.colorScheme;
    final laranja = saturation(scheme.primary);

    group(entry.key, () {
      test('primary continua laranja', () {
        expect(scheme.primary, isNot(Colors.grey));
        expect(laranja, greaterThan(.5));
      });

      test('surfaceTint está desligado (sem lavagem de cor por elevação)', () {
        expect(scheme.surfaceTint, Colors.transparent);
      });

      test('superfícies de menu/sheet/dialog são neutras, não laranja', () {
        final superficies = {
          'surfaceContainer': scheme.surfaceContainer,
          'surfaceContainerLow': scheme.surfaceContainerLow,
          'surfaceContainerHigh': scheme.surfaceContainerHigh,
          'surfaceContainerHighest': scheme.surfaceContainerHighest,
        };
        for (final MapEntry(:key, value: cor) in superficies.entries) {
          expect(
            saturation(cor),
            lessThan(.1),
            reason:
                '$key tem saturação ${saturation(cor).toStringAsFixed(3)} — '
                'deveria ser cinza neutro (< 0.1), não um tom de laranja.',
          );
        }
      });

      test('PopupMenu usa a mesma superfície neutra', () {
        expect(tema.popupMenuTheme.color, scheme.surfaceContainer);
        expect(saturation(tema.popupMenuTheme.color!), lessThan(.1));
      });

      test('BottomSheet (o "menu de escolha" do garçom) é neutro', () {
        final cor = tema.bottomSheetTheme.modalBackgroundColor;
        expect(cor, isNotNull);
        expect(saturation(cor!), lessThan(.1));
      });

      test('Dialog é neutro', () {
        final cor = tema.dialogTheme.backgroundColor;
        expect(cor, isNotNull);
        expect(saturation(cor!), lessThan(.1));
      });
    });
  }

  test('no escuro, a superfície do bottom sheet é realmente escura (preta)', () {
    final scheme = AppTheme.materialDark().colorScheme;
    // HSL lightness baixo = perto do preto. É literalmente o pedido do
    // usuário: "fundo... preto e não laranja".
    expect(HSLColor.fromColor(scheme.surfaceContainerLow).lightness, lessThan(.15));
  });
}
