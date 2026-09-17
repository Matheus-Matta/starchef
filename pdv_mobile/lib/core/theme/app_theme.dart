import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart' as shad;

import 'app_colors.dart';

/// Reexportado para nenhum arquivo que já usa `AppColors` precisar trocar de
/// import: o tema e a paleta continuam sendo a mesma porta de entrada.
export 'app_colors.dart';

/// Tokens visuais do app do garçom, no mesmo formato do PDV desktop
/// (`flutter/lib/core/theme/app_theme.dart`).
///
/// Mesma montagem dos dois lados: os componentes shadcn desenham as telas e o
/// Material continua atrás para diálogos, snackbars, popups e teclado. Os dois
/// temas são construídos a partir dos MESMOS tokens, e é isso que faz caixa e
/// salão parecerem o mesmo produto.
///
/// Duas medidas fogem do desktop de propósito, e só duas:
///
/// * [controlHeight] é maior — o aparelho é operado em pé, com uma mão, no
///   meio do salão;
/// * a tipografia fica no tamanho padrão do Material, sem o "um ponto a menos"
///   do desktop, porque a distância do olho até a tela é outra.
///
/// Todo o resto (raio, paleta, escala de respiro, estrutura do tema) é o mesmo
/// número dos dois lados.
abstract final class AppTheme {
  /// O mesmo raio do PDV. Cartão, campo, botão e selo do salão fecham o canto
  /// exatamente como os do caixa.
  static const radius = BorderRadius.all(Radius.circular(4));

  /// Altura de TODO controle de uma linha: campo, botão e item selecionável.
  ///
  /// Um número só, como no desktop — quando cada tipo escolhia a própria
  /// altura, uma folha com campo e botão saía em escadinha. Aqui ele é também
  /// o alvo de toque mínimo: controle menor que isso vira erro de lançamento.
  static const controlHeight = 52.0;

  /// Escala de respiro. Três valores, um por papel: dentro de uma linha, entre
  /// irmãos de uma lista, e entre blocos de assunto diferente.
  ///
  /// Existe pelo mesmo motivo de [controlHeight]: cada tela escolhia 8, 10, 12
  /// ou 14 por conta própria e nenhuma margem batia com a da tela vizinha.
  static const gapTight = 6.0;
  static const gap = 10.0;
  static const gapLoose = 16.0;

  /// Margem entre o conteúdo e a borda da tela.
  static const screenPadding = EdgeInsets.all(gapLoose);

  /// Respiro em volta de uma faixa de aviso quando ela aparece entre o
  /// cabeçalho e o conteúdo. Fica aqui, e não em cada faixa, porque as três
  /// (atualização, dados de cache, fila offline) podem aparecer empilhadas —
  /// e empilhadas com respiros diferentes o topo da tela fica torto.
  static const bannerPadding = EdgeInsets.fromLTRB(gapLoose, 12, gapLoose, 0);

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
        primary: dark ? AppColors.orangeLight : AppColors.orange,
        primaryForeground: Colors.white,
        secondary: dark ? AppColors.zinc800 : AppColors.zinc100,
        secondaryForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        muted: dark ? AppColors.zinc800 : AppColors.zinc100,
        mutedForeground: dark ? AppColors.zinc400 : AppColors.zinc500,
        accent: dark ? AppColors.zinc800 : AppColors.zinc100,
        accentForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        border: dark ? AppColors.zinc800 : AppColors.zinc200,
        input: dark ? AppColors.zinc800 : AppColors.zinc200,
        ring: dark ? AppColors.orangeLight : AppColors.orange,
      ),
    );
  }

  static ThemeData _material(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final primary = dark ? AppColors.orangeLight : AppColors.orange;
    final surface = dark ? AppColors.zinc900 : Colors.white;
    final ground = dark ? AppColors.zinc950 : AppColors.zinc50;
    final border = dark ? AppColors.zinc800 : AppColors.zinc200;
    final muted = dark ? AppColors.zinc400 : AppColors.zinc500;
    final scheme = _scheme(brightness, primary: primary);
    final text = ThemeData(brightness: brightness).textTheme.apply(
      bodyColor: scheme.onSurface,
      displayColor: scheme.onSurface,
    );

    return ThemeData(
      brightness: brightness,
      useMaterial3: true,
      colorScheme: scheme,
      scaffoldBackgroundColor: ground,
      textTheme: text,
      dividerColor: border,
      appBarTheme: AppBarTheme(
        backgroundColor: surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        shape: Border(bottom: BorderSide(color: border)),
        titleTextStyle: text.titleMedium?.copyWith(
          color: scheme.onSurface,
          fontWeight: FontWeight.w800,
        ),
      ),
      cardTheme: CardThemeData(
        color: surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: border),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surface,
        hintStyle: TextStyle(color: muted, fontWeight: FontWeight.w400),
        labelStyle: TextStyle(color: muted),
        // Rótulo ACIMA da caixa, nunca dentro: dentro, ele empurra o conteúdo
        // e o campo fica mais alto que o botão da mesma folha.
        floatingLabelBehavior: FloatingLabelBehavior.always,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 14,
        ),
        constraints: const BoxConstraints(minHeight: controlHeight),
        border: _inputBorder(border),
        enabledBorder: _inputBorder(border),
        focusedBorder: _inputBorder(primary, width: 1.6),
        errorBorder: _inputBorder(scheme.error),
        focusedErrorBorder: _inputBorder(scheme.error, width: 1.6),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, controlHeight),
          backgroundColor: primary,
          foregroundColor: Colors.white,
          disabledBackgroundColor: scheme.surfaceContainerHigh,
          disabledForegroundColor: muted,
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, controlHeight),
          foregroundColor: scheme.onSurface,
          side: BorderSide(color: border),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          // 48 px, e não [controlHeight]: aqui o alvo é o ícone sozinho, e 48
          // é o mínimo de toque do Material. O desktop pode encolher esse
          // número porque lá quem mira é o ponteiro do mouse.
          minimumSize: const Size.square(48),
          iconSize: 22,
          shape: const RoundedRectangleBorder(borderRadius: radius),
        ),
      ),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
        side: BorderSide(color: border),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: scheme.surfaceContainer,
        selectedColor: scheme.primaryContainer,
        side: BorderSide(color: border),
        shape: const RoundedRectangleBorder(borderRadius: radius),
        labelStyle: TextStyle(
          color: scheme.onSurface,
          fontWeight: FontWeight.w600,
        ),
      ),
      listTileTheme: ListTileThemeData(
        shape: const RoundedRectangleBorder(borderRadius: radius),
        iconColor: muted,
        titleTextStyle: text.bodyLarge?.copyWith(
          color: scheme.onSurface,
          fontWeight: FontWeight.w600,
        ),
        subtitleTextStyle: text.bodySmall?.copyWith(color: muted),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: primary,
        linearTrackColor: scheme.surfaceContainerHigh,
      ),
      snackBarTheme: const SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
      ),
      // Fixados explicitamente (em vez de confiar no token M3 default de cada
      // um) para não depender de qual `surfaceContainer*` cada widget escolhe
      // por padrão — isso muda entre versões do Flutter.
      popupMenuTheme: PopupMenuThemeData(
        color: scheme.surfaceContainer,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: border),
        ),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surfaceContainerLow,
        modalBackgroundColor: scheme.surfaceContainerLow,
        surfaceTintColor: Colors.transparent,
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: scheme.surfaceContainerHigh,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(borderRadius: radius),
      ),
    );
  }

  /// `ColorScheme.fromSeed` deriva TODAS as superfícies (inclusive as que o
  /// PopupMenu, o BottomSheet e o Dialog usam) do matiz da cor semente — com
  /// `primary` laranja, isso pinta o fundo desses componentes de um
  /// laranja-acinzentado em vez de neutro. Sobrescrevemos os tons de superfície
  /// para a mesma escala zinc que o cartão shadcn já usa, para o Material parar
  /// de "vazar" laranja onde só devia haver cinza/preto.
  static ColorScheme _scheme(Brightness brightness, {required Color primary}) {
    final dark = brightness == Brightness.dark;
    return ColorScheme.fromSeed(
      seedColor: primary,
      brightness: brightness,
    ).copyWith(
      primary: primary,
      surface: dark ? AppColors.zinc900 : Colors.white,
      onSurface: dark ? AppColors.zinc50 : AppColors.zinc900,
      onSurfaceVariant: dark ? AppColors.zinc400 : AppColors.zinc500,
      outline: dark ? AppColors.zinc800 : AppColors.zinc200,
      outlineVariant: dark ? AppColors.zinc800 : AppColors.zinc200,
      // Sem isso, todo componente elevado (Card, AppBar, Dialog, Menu,
      // BottomSheet) recebe uma lavagem semitransparente da cor primária
      // proporcional à elevação — é a causa mais comum de "por que esse menu
      // ficou laranja" em temas Material 3 com semente colorida.
      surfaceTint: Colors.transparent,
      surfaceContainerLowest: dark ? AppColors.zinc950 : Colors.white,
      surfaceContainerLow: dark ? AppColors.zinc900 : AppColors.zinc50,
      surfaceContainer: dark ? AppColors.zinc900 : AppColors.zinc100,
      surfaceContainerHigh: dark ? AppColors.zinc800 : AppColors.zinc200,
      surfaceContainerHighest: dark ? AppColors.zinc700 : AppColors.zinc300,
    );
  }

  static OutlineInputBorder _inputBorder(Color color, {double width = 1}) =>
      OutlineInputBorder(
        borderRadius: radius,
        borderSide: BorderSide(color: color, width: width),
      );
}
