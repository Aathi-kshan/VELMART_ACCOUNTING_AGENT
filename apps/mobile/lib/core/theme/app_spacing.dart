/// The 4 dp spacing scale (design.md §6). Use these instead of a bare
/// number so a screen's gaps stay on-grid — `AppSpacing.md`, never `17`.
abstract final class AppSpacing {
  static const double xs = 4;
  static const double sm = 8;
  static const double smMd = 12;
  static const double md = 16;
  static const double lg = 20;
  static const double xl = 24;
  static const double xxl = 32;
  static const double xxxl = 40;
  static const double huge = 48;
  static const double massive = 64;

  /// Default horizontal padding for a mobile screen body (design.md §6,
  /// "Default paddings").
  static const double screenHorizontal = md;

  /// Default card content padding (design.md's artboards pad a KPI/builder
  /// card 16px — `md`, not `lg`).
  static const double cardPadding = md;

  /// A denser card's padding — list rows, record-detail field rows, the
  /// reconciliation card. Off the 4dp grid on purpose: this is the
  /// artboards' own literal value (14px), not rounded to `smMd` (12) or
  /// `md` (16) because doing so visibly changes row density.
  static const double cardPaddingDense = 14;

  /// Default dialog content padding.
  static const double dialogPadding = xl;
}
