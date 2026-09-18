import 'package:flutter/material.dart';

/// Every color token in the Velmart design system (design.md §4.1). Values
/// come straight from the design handoff, not sampled ad hoc — a screen
/// should reach for one of these (or, more often, a [Theme.of] role built
/// from them in `app_theme.dart`) rather than writing a hex literal.
///
/// Brand green is the recognition color; it is deliberately *not* the
/// primary filled-action color (`brandPrimaryDark` is) — bright logo green
/// on white text fails contrast, so it stays reserved for accents and
/// selected states (design.md §22.2, §26.3).
abstract final class AppColors {
  // --- Brand ---------------------------------------------------------------
  static const brandPrimary = Color(0xFF44C045);
  static const brandPrimaryDark = Color(0xFF168B45);
  static const brandPrimaryDeep = Color(0xFF0F6F3B);
  static const brandPrimarySoft = Color(0xFFEAF8EC);
  static const brandPrimaryMuted = Color(0xFFCBE9CF);

  // --- Secondary blue/teal ---------------------------------------------------
  static const brandSecondary = Color(0xFF1E80A5);
  static const brandSecondaryDark = Color(0xFF155F7D);
  static const brandSecondarySoft = Color(0xFFEAF5F8);
  static const brandTeal = Color(0xFF4FA88B);

  // --- App surfaces ----------------------------------------------------------
  static const background = Color(0xFFF6F9F7);
  static const surface = Color(0xFFFFFFFF);
  static const surfaceSubtle = Color(0xFFF1F5F2);
  static const surfaceElevated = Color(0xFFFFFFFF);
  static const surfaceDisabled = Color(0xFFECEFEC);

  // --- Text --------------------------------------------------------------
  static const textPrimary = Color(0xFF17221B);
  static const textSecondary = Color(0xFF536159);
  static const textTertiary = Color(0xFF738078);
  static const textOnBrand = Color(0xFFFFFFFF);
  static const textDisabled = Color(0xFF99A39C);
  static const textLink = Color(0xFF155F7D);

  // --- Borders -----------------------------------------------------------
  static const border = Color(0xFFD8E2DB);
  static const borderStrong = Color(0xFFC1CEC5);
  static const borderFocus = Color(0xFF168B45);
  static const borderDisabled = Color(0xFFE5EAE6);

  /// The lightest divider — row dividers inside a card (field rows, audit
  /// rows, the reconciliation card's internal rule). Lighter than [border],
  /// which is for a card's own outline; using [border] for both reads as
  /// one heavy line where the mockups draw two different weights.
  static const hairline = Color(0xFFEDF1EE);

  // --- Semantic ------------------------------------------------------------
  static const success = Color(0xFF2F9959);
  static const successSoft = Color(0xFFEAF7EF);
  static const successBorder = Color(0xFFBFE3CD);
  static const warning = Color(0xFFC98A16);
  static const warningSoft = Color(0xFFFFF6DF);
  static const warningBorder = Color(0xFFEBD9A8);

  /// Warning text/icon color when it sits *on* [warningSoft] — [warning]
  /// itself is tuned for use on [surface] and is too light for AA contrast
  /// on the tinted background.
  static const warningText = Color(0xFF8A5E0C);
  static const error = Color(0xFFC94B4B);
  static const errorSoft = Color(0xFFFCECEC);
  static const errorBorder = Color(0xFFEFC9C9);

  /// Hover/pressed state for a destructive (error-colored) filled button —
  /// [error] itself is the resting state.
  static const errorDark = Color(0xFFA83C3C);
  static const info = Color(0xFF2B7EA0);
  static const infoSoft = Color(0xFFEAF5F8);
}
