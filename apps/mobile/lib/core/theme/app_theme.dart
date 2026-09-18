import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_component_themes.dart';
import 'app_typography.dart';

/// The single [ThemeData] Velmart renders with (design.md §23.1-23.2) —
/// [VelmartApp] reads only `AppTheme.light()`; every color/type/shape
/// decision lives here or in `app_colors.dart`/`app_typography.dart`/
/// `app_component_themes.dart`, never copied into a feature screen.
///
/// Only a light theme exists so far — the design handoff's dark variant
/// ("Velmart App - dark v1") is a separate deliverable this pass didn't
/// scope in.
abstract final class AppTheme {
  static ThemeData light() {
    final colorScheme = _lightColorScheme;
    final textTheme = AppTypography.textTheme(AppColors.textPrimary, AppColors.textSecondary);

    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: AppColors.background,
      canvasColor: AppColors.background,
      textTheme: textTheme,
      fontFamily: textTheme.bodyLarge?.fontFamily,
      splashFactory: InkSparkle.splashFactory,
      appBarTheme: AppComponentThemes.appBarTheme(textTheme),
      filledButtonTheme: AppComponentThemes.filledButtonTheme(textTheme),
      outlinedButtonTheme: AppComponentThemes.outlinedButtonTheme(textTheme),
      textButtonTheme: AppComponentThemes.textButtonTheme(textTheme),
      iconButtonTheme: AppComponentThemes.iconButtonTheme(),
      inputDecorationTheme: AppComponentThemes.inputDecorationTheme(textTheme),
      cardTheme: AppComponentThemes.cardTheme(),
      dialogTheme: AppComponentThemes.dialogTheme(textTheme),
      bottomSheetTheme: AppComponentThemes.bottomSheetTheme(),
      chipTheme: AppComponentThemes.chipTheme(textTheme),
      dividerTheme: AppComponentThemes.dividerTheme(),
      switchTheme: AppComponentThemes.switchTheme(),
      checkboxTheme: AppComponentThemes.checkboxTheme(),
      radioTheme: AppComponentThemes.radioTheme(),
      navigationBarTheme: AppComponentThemes.navigationBarTheme(textTheme),
      navigationRailTheme: AppComponentThemes.navigationRailTheme(textTheme),
      snackBarTheme: AppComponentThemes.snackBarTheme(textTheme),
      progressIndicatorTheme: AppComponentThemes.progressIndicatorTheme(),
      tooltipTheme: AppComponentThemes.tooltipTheme(textTheme),
      iconTheme: const IconThemeData(color: AppColors.textSecondary, size: 20),
      dividerColor: AppColors.border,
      focusColor: AppColors.borderFocus,
      hoverColor: AppColors.brandPrimarySoft,
      highlightColor: AppColors.brandPrimarySoft,
      splashColor: AppColors.brandPrimaryMuted,
      visualDensity: VisualDensity.standard,
    );
  }

  /// Design-token → [ColorScheme] mapping (design.md §4.1). `primary` is
  /// the deep filled-action green, not the bright recognition green — see
  /// `app_component_themes.dart`'s filled-button doc comment.
  static const _lightColorScheme = ColorScheme(
    brightness: Brightness.light,
    primary: AppColors.brandPrimaryDark,
    onPrimary: AppColors.textOnBrand,
    primaryContainer: AppColors.brandPrimarySoft,
    onPrimaryContainer: AppColors.brandPrimaryDeep,
    secondary: AppColors.brandSecondary,
    onSecondary: Colors.white,
    secondaryContainer: AppColors.brandSecondarySoft,
    onSecondaryContainer: AppColors.brandSecondaryDark,
    tertiary: AppColors.brandTeal,
    onTertiary: Colors.white,
    tertiaryContainer: AppColors.brandSecondarySoft,
    onTertiaryContainer: AppColors.brandSecondaryDark,
    error: AppColors.error,
    onError: Colors.white,
    errorContainer: AppColors.errorSoft,
    onErrorContainer: AppColors.error,
    surface: AppColors.surface,
    onSurface: AppColors.textPrimary,
    surfaceContainerLowest: Colors.white,
    surfaceContainerLow: AppColors.surfaceSubtle,
    surfaceContainer: AppColors.surfaceSubtle,
    surfaceContainerHigh: AppColors.surfaceDisabled,
    surfaceContainerHighest: AppColors.surfaceDisabled,
    onSurfaceVariant: AppColors.textSecondary,
    outline: AppColors.border,
    outlineVariant: AppColors.borderStrong,
    shadow: Colors.black,
    scrim: Colors.black,
    inverseSurface: AppColors.textPrimary,
    onInverseSurface: Colors.white,
    inversePrimary: AppColors.brandPrimary,
  );
}
