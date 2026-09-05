import 'package:flutter/material.dart';
import 'package:shadcn_ui/shadcn_ui.dart' as shad;

import 'app_colors.dart';

/// Tokens visuais compartilhados pelo Material e pelo flutter-shadcn-ui.
///
/// O PDV ainda depende de widgets Material para formulários e menus nativos.
/// Manter os dois temas alinhados permite migrar tela por tela sem alterar os
/// fluxos de operação.
abstract final class AppTheme {
  static const radius = BorderRadius.all(Radius.circular(4));

  /// Altura de TODO controle de uma linha: campo, select, data e botão.
  ///
  /// Um número só. Quando cada tipo escolhia a própria altura, a barra de
  /// filtros saía em escadinha — um campo de busca, três selects e um botão de
  /// data, cada um parando num lugar.
  static const controlHeight = 34.0;

  /// Altura de uma linha de tabela e do cabeçalho dela.
  ///
  /// Fica dois pixels acima de [controlHeight] porque a célula de ações traz
  /// botões: a linha precisa caber um controle inteiro mais o fio de respiro,
  /// senão volta o estouro de poucos pixels repetido em toda linha.
  static const tableRowHeight = controlHeight + 2;

  /// O que faz um botão medir [controlHeight] de verdade.
  ///
  /// `minimumSize` sozinho não basta, e essa foi a razão de a barra de filtros
  /// continuar em escadinha mesmo com todos os controles apontando para o mesmo
  /// número. Dois ajustes do Material entram na frente dele:
  ///
  /// * `tapTargetSize.padded` reserva 48 px de área de toque em volta do botão,
  ///   e é essa reserva — não o conteúdo — que definia a altura final.
  /// * [ThemeData.visualDensity] `compact` desconta 8 px de qualquer medida
  ///   pedida, então um `minimumSize` de 34 virava 26.
  ///
  /// Os dois juntos travavam todo botão em 40 px ao lado de campos de 34. Aqui
  /// eles saem do caminho: a altura passa a ser exatamente a que se pede.
  /// O PDV é operado em tela sensível ao toque, então o alvo continua sendo o
  /// botão inteiro — largo — e não um ícone solto de 34 px.
  static const _buttonDensity = VisualDensity.standard;
  static const _buttonTapTarget = MaterialTapTargetSize.shrinkWrap;

  /// Um ponto a menos em toda a tipografia: corpo 13, apoio 11, título 21.
  ///
  /// Um ponto fixo, e não uma porcentagem: a porcentagem produzia tamanhos
  /// quebrados (12,88 px) e encolhia o texto grande muito mais que o pequeno —
  /// justamente onde a legibilidade já era o limite.
  ///
  /// O atalho seria `TextTheme.apply(fontSizeDelta: -1)`, mas ele exige que
  /// TODO estilo do tema declare tamanho, e o tema padrão do Material traz
  /// slots sem tamanho: o atalho estourava numa asserção antes de a primeira
  /// tela aparecer. Aqui quem não declara tamanho passa intacto.
  static TextTheme _umPontoMenor(TextTheme base) {
    TextStyle? menor(TextStyle? style) {
      final size = style?.fontSize;
      return size == null ? style : style!.copyWith(fontSize: size - 1);
    }

    return base.copyWith(
      displayLarge: menor(base.displayLarge),
      displayMedium: menor(base.displayMedium),
      displaySmall: menor(base.displaySmall),
      headlineLarge: menor(base.headlineLarge),
      headlineMedium: menor(base.headlineMedium),
      headlineSmall: menor(base.headlineSmall),
      titleLarge: menor(base.titleLarge),
      titleMedium: menor(base.titleMedium),
      titleSmall: menor(base.titleSmall),
      bodyLarge: menor(base.bodyLarge),
      bodyMedium: menor(base.bodyMedium),
      bodySmall: menor(base.bodySmall),
      labelLarge: menor(base.labelLarge),
      labelMedium: menor(base.labelMedium),
      labelSmall: menor(base.labelSmall),
    );
  }

  static ThemeData light() => _buildMaterial(Brightness.light);
  static ThemeData dark() => _buildMaterial(Brightness.dark);

  static shad.ShadThemeData shadLight() => _buildShad(Brightness.light);
  static shad.ShadThemeData shadDark() => _buildShad(Brightness.dark);

  static shad.ShadThemeData _buildShad(Brightness brightness) {
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
        secondary: dark ? AppColors.zinc800 : const Color(0xFFF4F4F5),
        secondaryForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        muted: dark ? AppColors.zinc800 : const Color(0xFFF4F4F5),
        mutedForeground: dark ? AppColors.zinc400 : const Color(0xFF71717A),
        accent: dark ? AppColors.zinc800 : const Color(0xFFF4F4F5),
        accentForeground: dark ? AppColors.zinc50 : AppColors.zinc900,
        border: dark ? AppColors.zinc800 : AppColors.zinc200,
        input: dark ? AppColors.zinc800 : AppColors.zinc200,
        ring: dark ? const Color(0xFFF97316) : AppColors.orange,
      ),
    );
  }

  static ThemeData _buildMaterial(Brightness brightness) {
    final dark = brightness == Brightness.dark;
    final primary = dark ? const Color(0xFFF97316) : AppColors.orange;
    final surface = dark ? AppColors.zinc900 : Colors.white;
    final ground = dark ? AppColors.zinc950 : AppColors.zinc50;
    final border = dark ? AppColors.zinc800 : AppColors.zinc200;
    final muted = dark ? AppColors.zinc400 : const Color(0xFF71717A);
    final scheme =
        ColorScheme.fromSeed(
          seedColor: primary,
          brightness: brightness,
        ).copyWith(
          primary: primary,
          onPrimary: Colors.white,
          surface: surface,
          onSurface: dark ? AppColors.zinc50 : AppColors.zinc950,
          onSurfaceVariant: muted,
          surfaceContainerLowest: ground,
          surfaceContainerLow: surface,
          surfaceContainer: dark ? AppColors.zinc850 : const Color(0xFFF4F4F5),
          surfaceContainerHigh: dark
              ? AppColors.zinc800
              : const Color(0xFFE4E4E7),
          surfaceContainerHighest: dark
              ? AppColors.zinc800
              : const Color(0xFFD4D4D8),
          primaryContainer: dark
              ? const Color(0xFF431E0B)
              : const Color(0xFFFFF1E8),
          onPrimaryContainer: dark
              ? const Color(0xFFFFB27A)
              : AppColors.orangeDark,
          secondary: dark ? AppColors.zinc800 : const Color(0xFFF4F4F5),
          onSecondary: dark ? AppColors.zinc50 : AppColors.zinc900,
          outline: border,
          outlineVariant: border,
          error: dark ? const Color(0xFFEF4444) : AppColors.danger,
        );

    final textTheme = _umPontoMenor(
      ThemeData(brightness: brightness).textTheme.apply(
        fontFamily: 'Segoe UI',
        bodyColor: scheme.onSurface,
        displayColor: scheme.onSurface,
      ),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: ground,
      fontFamily: 'Segoe UI',
      textTheme: textTheme,
      dividerColor: border,
      visualDensity: VisualDensity.compact,
      appBarTheme: AppBarTheme(
        backgroundColor: surface,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        scrolledUnderElevation: 0,
        surfaceTintColor: Colors.transparent,
        shape: Border(bottom: BorderSide(color: border)),
        titleTextStyle: textTheme.titleMedium?.copyWith(
          color: scheme.onSurface,
          fontWeight: FontWeight.w700,
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
      dialogTheme: DialogThemeData(
        backgroundColor: dark ? AppColors.zinc850 : Colors.white,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: const RoundedRectangleBorder(borderRadius: radius),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        isDense: true,
        fillColor: surface,
        hintStyle: TextStyle(color: muted, fontWeight: FontWeight.w400),
        labelStyle: TextStyle(color: muted),
        // `floatingLabelBehavior: always` mantém o rótulo ACIMA da caixa em
        // vez de dentro dela. Dentro, ele empurra o conteúdo e o campo fica
        // mais alto que um botão da mesma barra — era a origem da escadinha
        // entre busca, selects e o seletor de período.
        floatingLabelBehavior: FloatingLabelBehavior.always,
        contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
        constraints: const BoxConstraints(minHeight: controlHeight),
        prefixIconConstraints: const BoxConstraints(
          minWidth: controlHeight,
          minHeight: controlHeight,
        ),
        suffixIconConstraints: const BoxConstraints(
          minWidth: controlHeight,
          minHeight: controlHeight,
        ),
        border: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: border),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: border),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.primary, width: 1.5),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.error),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: radius,
          borderSide: BorderSide(color: scheme.error, width: 1.5),
        ),
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          // A MESMA altura dos outros controles. Estava em 42 enquanto todo o
          // resto usava `controlHeight`, e um `ElevatedButton` ao lado de um
          // campo ou de um `FilledButton` saía dois pixels mais alto.
          minimumSize: const Size.fromHeight(controlHeight),
          visualDensity: _buttonDensity,
          tapTargetSize: _buttonTapTarget,
          backgroundColor: scheme.primary,
          foregroundColor: Colors.white,
          disabledBackgroundColor: scheme.surfaceContainerHigh,
          disabledForegroundColor: muted,
          elevation: 0,
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontSize: 14, fontWeight: FontWeight.w700),
        ),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(0, controlHeight),
          visualDensity: _buttonDensity,
          tapTargetSize: _buttonTapTarget,
          backgroundColor: primary,
          foregroundColor: Colors.white,
          disabledBackgroundColor: scheme.surfaceContainerHigh,
          disabledForegroundColor: muted,
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w700),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(0, controlHeight),
          visualDensity: _buttonDensity,
          tapTargetSize: _buttonTapTarget,
          foregroundColor: scheme.onSurface,
          side: BorderSide(color: border),
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          minimumSize: const Size(0, controlHeight),
          visualDensity: _buttonDensity,
          tapTargetSize: _buttonTapTarget,
          shape: const RoundedRectangleBorder(borderRadius: radius),
          textStyle: const TextStyle(fontWeight: FontWeight.w600),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(
          // Sem isto o botão de ícone fica em 40 px pela área de toque
          // reservada — e é ele que manda na altura da célula de ações de uma
          // tabela, onde o vizinho é um botão de 34.
          minimumSize: const Size(controlHeight, controlHeight),
          maximumSize: const Size.fromHeight(controlHeight),
          padding: const EdgeInsets.all(6),
          iconSize: 18,
          visualDensity: _buttonDensity,
          tapTargetSize: _buttonTapTarget,
          shape: const RoundedRectangleBorder(borderRadius: radius),
        ),
      ),
      checkboxTheme: CheckboxThemeData(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(2)),
        side: BorderSide(color: border),
        fillColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected) ? primary : surface,
        ),
      ),
      switchTheme: SwitchThemeData(
        thumbColor: WidgetStateProperty.resolveWith(
          (states) =>
              states.contains(WidgetState.selected) ? Colors.white : muted,
        ),
        trackColor: WidgetStateProperty.resolveWith(
          (states) => states.contains(WidgetState.selected)
              ? primary
              : scheme.surfaceContainerHigh,
        ),
        trackOutlineColor: WidgetStatePropertyAll(border),
      ),
      chipTheme: ChipThemeData(
        backgroundColor: scheme.surfaceContainer,
        selectedColor: scheme.primaryContainer,
        disabledColor: scheme.surfaceContainer,
        side: BorderSide(color: border),
        shape: const RoundedRectangleBorder(borderRadius: radius),
        labelStyle: TextStyle(
          color: scheme.onSurface,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      ),
      listTileTheme: ListTileThemeData(
        dense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
        shape: const RoundedRectangleBorder(borderRadius: radius),
        iconColor: scheme.onSurfaceVariant,
        titleTextStyle: textTheme.bodyMedium?.copyWith(
          color: scheme.onSurface,
          fontWeight: FontWeight.w600,
        ),
        subtitleTextStyle: textTheme.bodySmall?.copyWith(color: muted),
      ),
      dataTableTheme: DataTableThemeData(
        headingRowColor: WidgetStatePropertyAll(scheme.surfaceContainer),
        dataRowColor: WidgetStatePropertyAll(surface),
        dividerThickness: 1,
        // A linha vinha dos 48 px padrão do Material, e cada tela que achasse
        // pouco aumentava por conta própria — a lista de pedidos chegou a 68.
        // Com a régua no tema, uma tabela nova já nasce na densidade certa.
        headingRowHeight: tableRowHeight,
        dataRowMinHeight: tableRowHeight,
        dataRowMaxHeight: tableRowHeight,
        horizontalMargin: 10,
        columnSpacing: 18,
        headingTextStyle: textTheme.labelMedium?.copyWith(
          color: scheme.onSurfaceVariant,
          fontWeight: FontWeight.w800,
        ),
        dataTextStyle: textTheme.bodySmall?.copyWith(color: scheme.onSurface),
        decoration: BoxDecoration(
          color: surface,
          border: Border.all(color: border),
          borderRadius: radius,
        ),
      ),
      dropdownMenuTheme: DropdownMenuThemeData(
        textStyle: textTheme.bodyMedium,
        menuStyle: MenuStyle(
          backgroundColor: WidgetStatePropertyAll(surface),
          surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: radius),
          ),
          side: WidgetStatePropertyAll(BorderSide(color: border)),
        ),
      ),
      menuTheme: MenuThemeData(
        style: MenuStyle(
          backgroundColor: WidgetStatePropertyAll(surface),
          surfaceTintColor: const WidgetStatePropertyAll(Colors.transparent),
          shape: const WidgetStatePropertyAll(
            RoundedRectangleBorder(borderRadius: radius),
          ),
          side: WidgetStatePropertyAll(BorderSide(color: border)),
        ),
      ),
      popupMenuTheme: PopupMenuThemeData(
        color: surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: radius,
          side: BorderSide(color: border),
        ),
      ),
      progressIndicatorTheme: ProgressIndicatorThemeData(
        color: primary,
        linearTrackColor: scheme.surfaceContainerHigh,
        circularTrackColor: scheme.surfaceContainerHigh,
      ),
      scrollbarTheme: ScrollbarThemeData(
        thickness: const WidgetStatePropertyAll(6),
        radius: const Radius.circular(2),
        thumbColor: WidgetStatePropertyAll(
          scheme.onSurfaceVariant.withValues(alpha: .35),
        ),
        trackColor: WidgetStatePropertyAll(scheme.surfaceContainer),
      ),
      tooltipTheme: TooltipThemeData(
        decoration: BoxDecoration(
          color: dark ? AppColors.zinc800 : AppColors.zinc900,
          borderRadius: radius,
          border: Border.all(
            color: dark ? AppColors.zinc400 : AppColors.zinc800,
          ),
        ),
        textStyle: const TextStyle(color: Colors.white, fontSize: 12),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: surface,
        modalBackgroundColor: surface,
        surfaceTintColor: Colors.transparent,
        shape: const RoundedRectangleBorder(borderRadius: radius),
      ),
      snackBarTheme: SnackBarThemeData(
        backgroundColor: dark ? AppColors.zinc850 : AppColors.zinc900,
        contentTextStyle: const TextStyle(color: Colors.white),
        shape: const RoundedRectangleBorder(borderRadius: radius),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
}
