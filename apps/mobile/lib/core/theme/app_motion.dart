/// Interaction-feedback durations (design.md §31: "target ordinary
/// interaction feedback in roughly 100-250 ms"; approved patterns are route
/// fade/slide, sheet slide-up, card hover elevation, save confirmation —
/// never a decorative animation). Most of these durations are already
/// Flutter's own defaults for the widgets in question (route transitions,
/// `AnimatedContainer`); this exists so a screen that *does* need an
/// explicit `Duration` reaches for a token instead of picking a number.
abstract final class AppMotion {
  static const Duration fast = Duration(milliseconds: 120);
  static const Duration base = Duration(milliseconds: 180);
  static const Duration slow = Duration(milliseconds: 250);
}
