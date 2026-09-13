import 'package:flutter/material.dart';

import '../money/money.dart';

/// The single widget that renders money (plan section 22.3) — `Rs. 35,000.00`
/// via `Money.format()`, never an ad hoc `$value` interpolation that would
/// eventually format a raw wire string or a double somewhere.
class AmountText extends StatelessWidget {
  const AmountText(this.value, {super.key, this.style, this.colorByValue = false});

  /// A wire-format string (`"35000.00"`) or an already-parsed [Money].
  final Object? value;
  final TextStyle? style;

  /// Render negative amounts in the theme's error colour — useful in a
  /// ledger-style table, not wanted in a plain form field.
  final bool colorByValue;

  @override
  Widget build(BuildContext context) {
    final money = _resolve(value);
    if (money == null) return const SizedBox.shrink();

    final baseStyle = style ?? DefaultTextStyle.of(context).style;
    final color = colorByValue && money.isNegative
        ? Theme.of(context).colorScheme.error
        : baseStyle.color;

    return Text(money.format(), style: baseStyle.copyWith(color: color));
  }

  static Money? _resolve(Object? value) {
    if (value == null) return null;
    if (value is Money) return value;
    if (value is String && value.isNotEmpty) {
      try {
        return Money.parse(value);
      } on FormatException {
        return null;
      }
    }
    return null;
  }
}
