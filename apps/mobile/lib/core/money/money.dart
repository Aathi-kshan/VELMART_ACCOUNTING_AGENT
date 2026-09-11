/// Money as `int` minor units — never `double` (plan section 9.1).
///
/// Dart's `double` is IEEE-754 and will silently turn `Rs. 812,400.00` into
/// `Rs. 812,399.99` after enough arithmetic. Money crosses the wire as a
/// string (`"35000.00"`) and is parsed here into an integer count of cents —
/// LKR has two decimal places, matching the server's `NUMERIC(14,2)`.
class Money {
  const Money._(this.minorUnits);

  /// The exact value in the smallest currency unit (cents), never a float.
  final int minorUnits;

  static const Money zero = Money._(0);

  /// Parse the wire format: a decimal string with at most 2 fractional
  /// digits, e.g. `"35000.00"`, `"35000"`, `"-1234.5"`.
  factory Money.parse(String value) {
    final trimmed = value.trim();
    if (trimmed.isEmpty) {
      throw FormatException('Empty string is not a money value');
    }

    final negative = trimmed.startsWith('-');
    final unsigned = negative ? trimmed.substring(1) : trimmed;

    final parts = unsigned.split('.');
    if (parts.length > 2 || parts.any((p) => p.isEmpty && p != parts.last)) {
      throw FormatException('Not a valid money value: $value');
    }

    final wholePart = parts[0];
    if (wholePart.isEmpty || !_isDigits(wholePart)) {
      throw FormatException('Not a valid money value: $value');
    }

    var fractionPart = parts.length == 2 ? parts[1] : '';
    if (fractionPart.isNotEmpty && !_isDigits(fractionPart)) {
      throw FormatException('Not a valid money value: $value');
    }
    if (fractionPart.length > 2) {
      throw FormatException('Money supports at most 2 decimal places: $value');
    }
    fractionPart = fractionPart.padRight(2, '0');

    final whole = int.parse(wholePart);
    final fraction = int.parse(fractionPart);
    final total = whole * 100 + fraction;
    return Money._(negative ? -total : total);
  }

  /// Build directly from a known count of minor units (cents).
  factory Money.fromMinorUnits(int minorUnits) => Money._(minorUnits);

  static bool _isDigits(String s) => RegExp(r'^\d+$').hasMatch(s);

  /// The wire format: always two decimal places, always a string.
  String toApiString() {
    final negative = minorUnits < 0;
    final abs = minorUnits.abs();
    final whole = abs ~/ 100;
    final fraction = abs % 100;
    final sign = negative ? '-' : '';
    return '$sign$whole.${fraction.toString().padLeft(2, '0')}';
  }

  /// A locale-agnostic display string, e.g. `Rs. 35,000.00`.
  String format({String currencySymbol = 'Rs.'}) {
    final negative = minorUnits < 0;
    final abs = minorUnits.abs();
    final whole = abs ~/ 100;
    final fraction = abs % 100;

    final wholeStr = whole.toString();
    final buffer = StringBuffer();
    for (var i = 0; i < wholeStr.length; i++) {
      if (i > 0 && (wholeStr.length - i) % 3 == 0) {
        buffer.write(',');
      }
      buffer.write(wholeStr[i]);
    }

    final sign = negative ? '-' : '';
    return '$sign$currencySymbol ${buffer.toString()}.${fraction.toString().padLeft(2, '0')}';
  }

  Money operator +(Money other) => Money._(minorUnits + other.minorUnits);
  Money operator -(Money other) => Money._(minorUnits - other.minorUnits);
  Money operator -() => Money._(-minorUnits);

  bool operator <(Money other) => minorUnits < other.minorUnits;
  bool operator <=(Money other) => minorUnits <= other.minorUnits;
  bool operator >(Money other) => minorUnits > other.minorUnits;
  bool operator >=(Money other) => minorUnits >= other.minorUnits;

  bool get isNegative => minorUnits < 0;
  bool get isZero => minorUnits == 0;

  @override
  bool operator ==(Object other) => other is Money && other.minorUnits == minorUnits;

  @override
  int get hashCode => minorUnits.hashCode;

  @override
  String toString() => format();
}
