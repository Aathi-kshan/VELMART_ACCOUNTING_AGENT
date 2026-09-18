import 'package:flutter/material.dart';

import 'app_colors.dart';
import 'app_radii.dart';
import 'app_spacing.dart';

/// Dialog/sheet elevation (design.md §7.2: "modal dialogs: 6-12"). Material's
/// `elevation` is a numeric depth, not the artboards' literal
/// `0 6px 20px rgba(23,34,27,.28)` — `shadowColor` gets it into the right
/// hue rather than Flutter's default black.
const double _overlayElevation = 8;

/// One function per Material component theme (design.md §9-12, §23.2),
/// each built from [AppColors]/the app's [TextTheme] rather than a hex
/// literal — `app_theme.dart` assembles these into one [ThemeData]. Split
/// out from `app_theme.dart` so each component's rules are easy to find and
/// change independently, per design.md's own recommended file structure.
abstract final class AppComponentThemes {
  /// 44-48 dp height, 8 dp radius, deep green fill (design.md §9.1) — the
  /// bright logo green is reserved for recognition, not filled actions
  /// (§22.2, §26.3: it fails contrast with white text).
  static FilledButtonThemeData filledButtonTheme(TextTheme textTheme) => FilledButtonThemeData(
    style: FilledButton.styleFrom(
      backgroundColor: AppColors.brandPrimaryDark,
      disabledBackgroundColor: AppColors.surfaceDisabled,
      disabledForegroundColor: AppColors.textDisabled,
      foregroundColor: AppColors.textOnBrand,
      textStyle: textTheme.labelLarge,
      minimumSize: const Size(64, 48),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
      shape: const RoundedRectangleBorder(borderRadius: AppRadii.smRadius),
    ).copyWith(
      overlayColor: WidgetStateProperty.resolveWith(
        (states) => states.contains(WidgetState.pressed) ? AppColors.brandPrimaryDeep : null,
      ),
    ),
  );

  /// Outline/soft-toned button (design.md §9.2) — used for Cancel, Filter,
  /// Reset.
  static OutlinedButtonThemeData outlinedButtonTheme(TextTheme textTheme) =>
      OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: AppColors.brandPrimaryDeep,
          disabledForegroundColor: AppColors.textDisabled,
          side: const BorderSide(color: AppColors.border),
          textStyle: textTheme.labelLarge,
          minimumSize: const Size(64, 48),
          padding: const EdgeInsets.symmetric(horizontal: AppSpacing.lg),
          shape: const RoundedRectangleBorder(borderRadius: AppRadii.smRadius),
        ),
      );

  /// Low-risk navigation/supporting actions (design.md §9.3) — View all,
  /// Clear filters, Show details.
  static TextButtonThemeData textButtonTheme(TextTheme textTheme) => TextButtonThemeData(
    style: TextButton.styleFrom(
      foregroundColor: AppColors.brandPrimaryDeep,
      disabledForegroundColor: AppColors.textDisabled,
      textStyle: textTheme.labelLarge,
      minimumSize: const Size(44, 44),
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
      shape: const RoundedRectangleBorder(borderRadius: AppRadii.smRadius),
    ),
  );

  /// Deliberately no `foregroundColor` here — `IconButtonThemeData` outranks
  /// each variant's own M3 defaults, so setting one blanket color would mute
  /// `IconButton.filled`'s white-on-brand icon to this same grey everywhere
  /// (the AI chat send button's actual bug). A plain `IconButton` already
  /// resolves to `colorScheme.onSurfaceVariant`, which this theme maps to
  /// `AppColors.textSecondary` anyway — so leaving color to M3 keeps a plain
  /// icon button's look unchanged while letting filled variants stay
  /// correctly green/white.
  static IconButtonThemeData iconButtonTheme() =>
      IconButtonThemeData(style: IconButton.styleFrom(minimumSize: const Size(44, 44)));

  /// 44-48 dp white field, 1 dp border, 8 dp radius, brand-green focus ring
  /// (design.md §10.1-10.2). Error styling never relies on color alone —
  /// the error string itself carries the meaning; this only sets its color.
  static InputDecorationThemeData inputDecorationTheme(TextTheme textTheme) =>
      InputDecorationThemeData(
        filled: true,
        fillColor: AppColors.surface,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.smMd,
        ),
        labelStyle: textTheme.bodyLarge?.copyWith(color: AppColors.textSecondary),
        floatingLabelStyle: textTheme.bodySmall?.copyWith(color: AppColors.brandPrimaryDark),
        helperStyle: textTheme.bodySmall,
        hintStyle: textTheme.bodyLarge?.copyWith(color: AppColors.textTertiary),
        errorStyle: textTheme.bodySmall?.copyWith(color: AppColors.error),
        errorMaxLines: 3,
        border: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.border),
        ),
        enabledBorder: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.border),
        ),
        disabledBorder: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.borderDisabled),
        ),
        focusedBorder: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.borderFocus, width: 2),
        ),
        errorBorder: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.error),
        ),
        focusedErrorBorder: const OutlineInputBorder(
          borderRadius: AppRadii.smRadius,
          borderSide: BorderSide(color: AppColors.error, width: 2),
        ),
      );

  /// White surface, 1 dp border, 12 dp radius, minimal shadow (design.md
  /// §11.1) — the default application card.
  static CardThemeData cardTheme() => const CardThemeData(
    color: AppColors.surface,
    surfaceTintColor: Colors.transparent,
    elevation: 0,
    margin: EdgeInsets.zero,
    shape: RoundedRectangleBorder(
      borderRadius: AppRadii.mdRadius,
      side: BorderSide(color: AppColors.border),
    ),
  );

  /// 16 dp radius, elevated (design.md §7.1-7.2, §11.4).
  static DialogThemeData dialogTheme(TextTheme textTheme) => DialogThemeData(
    backgroundColor: AppColors.surfaceElevated,
    surfaceTintColor: Colors.transparent,
    elevation: _overlayElevation,
    shadowColor: AppColors.textPrimary,
    shape: const RoundedRectangleBorder(borderRadius: AppRadii.lgRadius),
    titleTextStyle: textTheme.titleLarge,
    contentTextStyle: textTheme.bodyLarge,
  );

  static BottomSheetThemeData bottomSheetTheme() => BottomSheetThemeData(
    backgroundColor: AppColors.surfaceElevated,
    surfaceTintColor: Colors.transparent,
    elevation: _overlayElevation,
    modalElevation: _overlayElevation,
    shadowColor: AppColors.textPrimary,
    shape: const RoundedRectangleBorder(
      borderRadius: BorderRadius.vertical(top: Radius.circular(AppRadii.lg)),
    ),
  );

  /// Pill-shaped, tinted (design.md §10.7, §10.6 SELECT chevron/status use)
  /// — used for MULTI_SELECT chips and status chips alike.
  static ChipThemeData chipTheme(TextTheme textTheme) => ChipThemeData(
    backgroundColor: AppColors.surfaceSubtle,
    selectedColor: AppColors.brandPrimarySoft,
    disabledColor: AppColors.surfaceDisabled,
    labelStyle: textTheme.labelLarge?.copyWith(color: AppColors.textPrimary),
    secondaryLabelStyle: textTheme.labelLarge?.copyWith(color: AppColors.brandPrimaryDeep),
    side: const BorderSide(color: AppColors.border),
    shape: const StadiumBorder(),
    padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm),
  );

  static DividerThemeData dividerTheme() =>
      const DividerThemeData(color: AppColors.border, thickness: 1, space: 1);

  static SwitchThemeData switchTheme() => SwitchThemeData(
    thumbColor: const WidgetStatePropertyAll(AppColors.surface),
    trackColor: WidgetStateProperty.resolveWith(
      (states) =>
          states.contains(WidgetState.selected) ? AppColors.brandPrimaryDark : AppColors.border,
    ),
    trackOutlineColor: const WidgetStatePropertyAll(Colors.transparent),
  );

  static CheckboxThemeData checkboxTheme() => CheckboxThemeData(
    fillColor: WidgetStateProperty.resolveWith(
      (states) => states.contains(WidgetState.selected)
          ? AppColors.brandPrimaryDark
          : Colors.transparent,
    ),
    checkColor: const WidgetStatePropertyAll(AppColors.textOnBrand),
    side: const BorderSide(color: AppColors.border, width: 1.5),
    shape: const RoundedRectangleBorder(borderRadius: AppRadii.xsRadius),
  );

  static RadioThemeData radioTheme() => RadioThemeData(
    fillColor: WidgetStateProperty.resolveWith(
      (states) => states.contains(WidgetState.selected)
          ? AppColors.brandPrimaryDark
          : AppColors.textTertiary,
    ),
  );

  /// Bottom navigation (design.md §12.2) — selected item gets the soft
  /// brand tint, never the bright logo green as a fill.
  static NavigationBarThemeData navigationBarTheme(TextTheme textTheme) => NavigationBarThemeData(
    backgroundColor: AppColors.surface,
    indicatorColor: AppColors.brandPrimarySoft,
    surfaceTintColor: Colors.transparent,
    labelTextStyle: WidgetStateProperty.resolveWith(
      (states) => textTheme.labelMedium?.copyWith(
        color: states.contains(WidgetState.selected)
            ? AppColors.brandPrimaryDeep
            : AppColors.textTertiary,
        fontWeight: states.contains(WidgetState.selected) ? FontWeight.w600 : FontWeight.w500,
      ),
    ),
    iconTheme: WidgetStateProperty.resolveWith(
      (states) => IconThemeData(
        color: states.contains(WidgetState.selected)
            ? AppColors.brandPrimaryDeep
            : AppColors.textTertiary,
      ),
    ),
  );

  /// Navigation rail (design.md §12.3, tablet width).
  static NavigationRailThemeData navigationRailTheme(TextTheme textTheme) =>
      NavigationRailThemeData(
        backgroundColor: AppColors.surface,
        selectedIconTheme: const IconThemeData(color: AppColors.brandPrimaryDeep),
        unselectedIconTheme: const IconThemeData(color: AppColors.textTertiary),
        selectedLabelTextStyle: textTheme.labelMedium?.copyWith(
          color: AppColors.brandPrimaryDeep,
          fontWeight: FontWeight.w600,
        ),
        unselectedLabelTextStyle: textTheme.labelMedium?.copyWith(color: AppColors.textTertiary),
        useIndicator: true,
        indicatorColor: AppColors.brandPrimarySoft,
      );

  /// Flat, no auto-tint app bar (design.md §12.5) — the shell owns
  /// navigation chrome; this just keeps the app bar itself quiet.
  static AppBarThemeData appBarTheme(TextTheme textTheme) => AppBarThemeData(
    backgroundColor: AppColors.surface,
    foregroundColor: AppColors.textPrimary,
    surfaceTintColor: Colors.transparent,
    elevation: 0,
    scrolledUnderElevation: 1,
    centerTitle: false,
    titleTextStyle: textTheme.titleMedium,
    iconTheme: const IconThemeData(color: AppColors.textPrimary),
  );

  static SnackBarThemeData snackBarTheme(TextTheme textTheme) => SnackBarThemeData(
    backgroundColor: AppColors.textPrimary,
    contentTextStyle: textTheme.bodyLarge?.copyWith(color: AppColors.textOnBrand),
    behavior: SnackBarBehavior.floating,
    shape: const RoundedRectangleBorder(borderRadius: AppRadii.smRadius),
  );

  static ProgressIndicatorThemeData progressIndicatorTheme() =>
      const ProgressIndicatorThemeData(color: AppColors.brandPrimaryDark);

  static TooltipThemeData tooltipTheme(TextTheme textTheme) => TooltipThemeData(
    decoration: BoxDecoration(color: AppColors.textPrimary, borderRadius: AppRadii.xsRadius),
    textStyle: textTheme.bodySmall?.copyWith(color: AppColors.textOnBrand),
  );
}
