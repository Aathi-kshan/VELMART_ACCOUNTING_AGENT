import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

/// The Velmart type scale (design.md §5), built on Inter.
///
/// Design.md names 12 tokens (`display`, `h1`, `h2`, `h3`, `title`, `body`,
/// `bodyMedium`, `bodySmall`, `label`, `caption`, `data`, `dataStrong`) —
/// more than Flutter's 15-slot [TextTheme] has natural 1:1 names for, and
/// two (`data`/`dataStrong`, for table cells) that aren't part of
/// [TextTheme] at all. [textTheme] maps the 12 onto the slots screens
/// already call (`headlineMedium` for a login-style brand heading,
/// `titleLarge` for a card/section title, `bodyLarge` for default content,
/// and so on); [data]/[dataStrong] are exposed separately for table cells
/// and key financial values.
abstract final class AppTypography {
  static TextTheme textTheme(Color primaryColor, Color secondaryColor) {
    TextStyle style(double size, FontWeight weight, {Color? color, double? height}) =>
        GoogleFonts.inter(
          fontSize: size,
          fontWeight: weight,
          color: color ?? primaryColor,
          height: height,
        );

    return TextTheme(
      // display — major page/brand heading (30/700). Reserved for the login
      // screen's brand hero moment; no other screen has anything this large.
      displayLarge: style(30, FontWeight.w700, height: 1.2),
      displayMedium: style(30, FontWeight.w700, height: 1.2),
      displaySmall: style(26, FontWeight.w700, height: 1.2),
      // h1 — a top-level tab's own title: Home, Pages, More (26/700). Kept
      // as-is; it was already correct and already the only thing calling
      // headlineLarge.
      headlineLarge: style(26, FontWeight.w700, height: 1.2),
      // A drilled-in screen's own title — record list, record detail,
      // reconciliation, page builder (24/700, artboard "screen title").
      // headlineMedium was previously mapped to 30 and had exactly one
      // caller (`home_screen.dart`'s hero KPI value), which already
      // overrides `fontSize` via `.copyWith` — so repurposing this slot to
      // 24 changes nothing there and gives every future "back-arrow +
      // title" screen header a correct token to reach for.
      headlineMedium: style(24, FontWeight.w700, height: 1.2),
      // A secondary panel/section title — the "Ask Velmart" header
      // (22/700). Kept as-is: already correct at its one real caller.
      headlineSmall: style(22, FontWeight.w700, height: 1.25),
      // h3 — card/section title (18/700). title — app-bar/subsection title
      // (16/650).
      titleLarge: style(18, FontWeight.w700, height: 1.25),
      titleMedium: style(16, FontWeight.w600, height: 1.3),
      titleSmall: style(12, FontWeight.w600, height: 1.3, color: secondaryColor),
      // body/bodyMedium/bodySmall — default content, important body text,
      // metadata (14/400, 14/550, 12/400).
      bodyLarge: style(14, FontWeight.w400, height: 1.45),
      bodyMedium: style(14, FontWeight.w600, height: 1.45),
      bodySmall: style(12, FontWeight.w400, height: 1.4, color: secondaryColor),
      // label — field labels/buttons (12/600). caption — secondary metadata
      // (11/500), reused for labelMedium/labelSmall since design.md has no
      // second micro-label token.
      labelLarge: style(14, FontWeight.w600, height: 1.3),
      labelMedium: style(11, FontWeight.w500, height: 1.35, color: secondaryColor),
      labelSmall: style(11, FontWeight.w500, height: 1.35, color: secondaryColor),
    );
  }

  /// Table cell value (design.md §5.2 `data`: 14/500) — not a [TextTheme]
  /// slot. Color is left to the call site (`AmountText`'s `colorByValue`,
  /// a plain cell's `onSurface`, ...).
  static TextStyle data({Color? color}) =>
      GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w500, color: color, height: 1.3);

  /// Key financial value (design.md §5.2 `dataStrong`: 14/650). Flutter's
  /// [FontWeight] only defines steps of 100 — 650 rounds down to 600 rather
  /// than up to 700, since design.md's own weight scale otherwise uses 700
  /// for headings and reserves that heavier weight for those, not table
  /// cells.
  static TextStyle dataStrong({Color? color}) =>
      GoogleFonts.inter(fontSize: 14, fontWeight: FontWeight.w600, color: color, height: 1.3);
}
