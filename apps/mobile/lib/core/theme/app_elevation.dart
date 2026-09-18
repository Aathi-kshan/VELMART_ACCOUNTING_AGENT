import 'package:flutter/material.dart';

/// Shadow tokens (design.md §7.2: base 0 / card 1 / floating 2-4 /
/// dialog 6-12). Cards themselves stay at `elevation: 0` with a border
/// (`app_component_themes.dart`'s own rationale: "prefer border + surface
/// separation over heavy shadows") — these three are for the surfaces
/// design.md explicitly does want elevated: a floating action button, and
/// a modal dialog or bottom sheet.
abstract final class AppElevation {
  /// Reserved for a surface that floats above cards without being a modal
  /// (a dropdown menu, a pinned toolbar) — not currently used by any
  /// component theme, kept so one doesn't get invented ad hoc later.
  static const List<BoxShadow> card = [
    BoxShadow(color: Color(0x0F17221B), offset: Offset(0, 1), blurRadius: 3),
  ];

  /// A floating action button — green-tinted, not neutral, so it reads as
  /// a brand action rather than generic elevation.
  static const List<BoxShadow> floating = [
    BoxShadow(color: Color(0x470F6F3B), offset: Offset(0, 4), blurRadius: 14),
  ];

  /// A modal dialog or bottom sheet.
  static const List<BoxShadow> overlay = [
    BoxShadow(color: Color(0x4717221B), offset: Offset(0, 6), blurRadius: 20),
  ];
}
