import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/money/money.dart';

// Mirrors apps/api/tests/test_money_precision.py — the client-side half of
// plan section 9.1's rule: money is int minor units, never double.
void main() {
  group('Money.parse', () {
    test('parses a whole amount', () {
      expect(Money.parse('35000').toApiString(), '35000.00');
    });

    test('parses two decimal places', () {
      expect(Money.parse('35000.50').toApiString(), '35000.50');
    });

    test('pads a single decimal place', () {
      expect(Money.parse('35000.5').toApiString(), '35000.50');
    });

    test('round-trips through the wire format', () {
      const original = '1234567.89';
      expect(Money.parse(original).toApiString(), original);
    });

    test('parses zero', () {
      expect(Money.parse('0').isZero, isTrue);
    });

    test('parses a negative amount', () {
      final money = Money.parse('-500.25');
      expect(money.isNegative, isTrue);
      expect(money.toApiString(), '-500.25');
    });

    test('rejects an empty string', () {
      expect(() => Money.parse(''), throwsFormatException);
    });

    test('rejects more than two decimal places', () {
      expect(() => Money.parse('1.234'), throwsFormatException);
    });

    test('rejects non-numeric input', () {
      expect(() => Money.parse('abc'), throwsFormatException);
    });

    test('rejects thousands separators', () {
      // The server never emits these; a client that silently accepted one
      // would parse "1,234.00" as a different, wrong number.
      expect(() => Money.parse('1,234.00'), throwsFormatException);
    });

    test('rejects a second decimal point', () {
      expect(() => Money.parse('12.34.56'), throwsFormatException);
    });
  });

  group('arithmetic never touches a double', () {
    test('adding two amounts stays exact', () {
      final total = Money.parse('0.10') + Money.parse('0.20');
      // The classic double failure: 0.1 + 0.2 != 0.3 in IEEE-754.
      expect(total.toApiString(), '0.30');
    });

    test('summing 100 cents equals exactly one rupee', () {
      var total = Money.zero;
      for (var i = 0; i < 100; i++) {
        total += Money.parse('0.01');
      }
      expect(total.toApiString(), '1.00');
    });

    test('subtraction', () {
      final result = Money.parse('100.00') - Money.parse('35.50');
      expect(result.toApiString(), '64.50');
    });

    test('unary negation', () {
      final money = Money.parse('50.00');
      expect((-money).toApiString(), '-50.00');
    });

    test('comparison operators', () {
      expect(Money.parse('10.00') < Money.parse('20.00'), isTrue);
      expect(Money.parse('20.00') > Money.parse('10.00'), isTrue);
      expect(Money.parse('10.00') <= Money.parse('10.00'), isTrue);
      expect(Money.parse('10.00') >= Money.parse('10.00'), isTrue);
    });

    test('equality is value-based', () {
      expect(Money.parse('35000.00'), equals(Money.parse('35000.00')));
      expect(Money.parse('35000.00') == Money.parse('35000.01'), isFalse);
    });
  });

  group('format', () {
    test('adds thousands separators and keeps cents when they are non-zero', () {
      expect(Money.parse('1234567.89').format(), 'Rs. 1,234,567.89');
    });

    test('omits cents for whole rupees', () {
      expect(Money.parse('250000.00').format(), 'Rs. 250,000');
      expect(Money.parse('42.00').format(), 'Rs. 42');
    });

    test('a custom currency symbol', () {
      expect(
        Money.parse('100.00').format(currencySymbol: r'$'),
        r'$ 100',
      );
    });
  });

  group('large amounts keep every digit', () {
    test('the value section 9.1 warns double corrupts', () {
      // Rs. 812,400.00 must never become 812,399.99.
      expect(Money.parse('812400.00').toApiString(), '812400.00');
    });
  });
}
