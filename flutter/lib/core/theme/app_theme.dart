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
  static const controlHeight = 40.0;

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

    final textTheme = ThemeData(brightness: brightness).textTheme.apply(
      fontFamily: 'Segoe UI',
      bodyColor: scheme.onSurface,
      displayColor: scheme.onSurface,
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
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
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
          foregroundColor: scheme.onSurface,
          side: BorderSide(color: border),
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
        horizontalMargin: 16,
        columnSpacing: 28,
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
