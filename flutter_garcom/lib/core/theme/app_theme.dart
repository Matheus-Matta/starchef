import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart' as shad;

/// Paleta compartilhada com o PDV desktop (`flutter/lib/core/theme`), para o
/// garçom e o caixa parecerem o mesmo produto.
abstract final class AppColors {
  static const orange = Color(0xFFEA580C);
  static const danger = Color(0xFFDC2626);
  static const success = Color(0xFF16A34A);
  static const warning = Color(0xFFD97706);
  static const zinc50 = Color(0xFFFAFAFA);
  static const zinc100 = Color(0xFFF4F4F5);
  static const zinc200 = Color(0xFFE4E4E7);
  static const zinc300 = Color(0xFFD4D4D8);
  static const zinc400 = Color(0xFFA1A1AA);
  static const zinc500 = Color(0xFF71717A);
  static const zinc700 = Color(0xFF3F3F46);
  static const zinc800 = Color(0xFF27272A);
  static const zinc900 = Color(0xFF18181B);
  static const zinc950 = Color(0xFF09090B);
}

/// Tema do app do garçom.
///
/// Mesmo par Material + shadcn do PDV: os componentes shadcn desenham as telas
/// e o Material continua atrás para diálogos, snackbars, popups e o teclado.
abstract final class AppTheme {
  static const radius = BorderRadius.all(Radius.circular(8));

  /// Alvo de toque mínimo. O aparelho é usado em pé, com uma mão e no meio do
  /// salão: controles menores que isso viram erro de lançamento.
  static const controlHeight = 52.0;

  static shad.ShadThemeData shadLight() => _shad(Brightness.light);
  static shad.ShadThemeData shadDark() => _shad(Brightness.dark);
  static ThemeData materialLight() => _material(Brightness.light);
  static ThemeData materialDark() => _material(Brightness.dark);

  static shad.ShadThemeData _shad(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final base = dark
        ? const shad.ShadOrangeColorScheme.dark()
        : const shad.ShadOrangeColorScheme.light();
    return shad.ShadThemeData(
      brightness: brightness,
      radius: radius,
      disableSecondaryBorder: true,
      colorScheme: base.copyWith(
        background: dark ? AppColors.zinc950 : AppColors.zinc50,
        foreground: dark ? AppColors.zinc50 : AppColors.zinc950,
        card: dark ? AppColors.zinc900 : Colors.white,
        cardForeground: dark ? AppColors.zinc50 : AppColors.zinc950,
        popover: dark ? AppColors.zinc900 : Colors.white,
        popoverForeground: dark ? AppColors.zinc50 : AppColors.zinc950,
        primary: dark ? const Color(0xFFF97316) : AppColors.orange,
        primaryForeground: Colors.white,
        secondary: dark ? AppColors.zinc800 : AppColors.zinc100,
        secondaryForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        muted: dark ? AppColors.zinc800 : AppColors.zinc100,
        mutedForeground: dark ? AppColors.zinc400 : AppColors.zinc500,
        accent: dark ? AppColors.zinc800 : AppColors.zinc100,
        accentForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        border: dark ? AppColors.zinc800 : AppColors.zinc200,
        input: dark ? AppColors.zinc800 : AppColors.zinc200,
        ring: dark ? const Color(0xFFF97316) : AppColors.orange,
      ),
    );
  }

  static ThemeData _material(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final primary = dark ? const Color(0xFFF97316) : AppColors.orange;
    final surface = dark ? AppColors.zinc900 : Colors.white;
    final ground = dark ? AppColors.zinc950 : AppColors.zinc50;
    final border = dark ? AppColors.zinc800 : AppColors.zinc200;
    final onSurface = dark ? AppColors.zinc50 : AppColors.zinc900;
    final onSurfaceVariant = dark ? AppColors.zinc400 : AppColors.zinc500;

    // `ColorScheme.fromSeed` deriva TODAS as superfícies (inclusive as que o
    // PopupMenu, o BottomSheet e o Dialog usam) do matiz da cor semente — com
    // `primary` laranja, isso pinta o fundo desses componentes de um
    // laranja-acinzentado em vez de neutro. Sobrescrevemos os tons de
    // superfície para a mesma escala zinc que o cartão shadcn já usa, para o
    // Material parar de "vazar" laranja onde só devia haver cinza/preto.
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: primary,
          brightness: brightness,
        ).copyWith(
          primary: primary,
          surface: surface,
          onSurface: onSurface,
          onSurfaceVariant: onSurfaceVariant,
          outlineVariant: border,
          // Sem isso, todo componente elevado (Card, AppBar, Dialog, Menu,
          // BottomSheet) recebe uma lavagem semitransparente da cor primária
          // proporcional à elevação — é a causa mais comum de "por que esse
          // menu ficou laranja" em temas Material 3 com semente colorida.
          surfaceTint: Colors.transparent,
          surfaceContainerLowest: dark ? AppColors.zinc950 : Colors.white,
          surfaceContainerLow: dark ? AppColors.zinc900 : AppColors.zinc50,
          surfaceContainer: dark ? AppColors.zinc900 : AppColors.zinc100,
          surfaceContainerHigh: dark ? AppColors.zinc800 : AppColors.zinc200,
          surfaceContainerHighest: dark
              ? AppColors.zinc700
              : AppColors.zinc300,
        );

    return ThemeData(
      brightness: brightness,
      useMaterial3: true,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: ground,
      dividerColor: border,
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
      ),
      // Fixados explicitamente (em vez de confiar no token M3 default de cada
      // um) para não depender de qual `surfaceContainer*` cada widget escolhe
      // por padrão — isso muda entre versões do Flutter.
      popupMenuTheme: PopupMenuThemeData(color: colorScheme.surfaceContainer),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: colorScheme.surfaceContainerLow,
        modalBackgroundColor: colorScheme.surfaceContainerLow,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: colorScheme.surfaceContainerHigh,
      ),
    );
  }
}
