import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/date/business_date.dart';

// Mirrors apps/api/tests/test_business_dates.py's parsing/display half —
// business_date itself is always server-derived (plan section 9.2); this
// only checks the client renders and round-trips it without drifting.
void main() {
  group('parseWireDate', () {
    test('parses a plain ISO date', () {
      final date = parseWireDate('2026-09-07');
      expect(date, isNotNull);
      expect(date!.year, 2026);
      expect(date.month, 9);
      expect(date.day, 7);
    });

    test('returns null for empty or malformed input', () {
      expect(parseWireDate(''), isNull);
      expect(parseWireDate('not-a-date'), isNull);
      expect(parseWireDate(null), isNull);
    });
  });

  group('formatDate', () {
    test('renders a human-readable date', () {
      expect(formatDate('2026-09-07'), '7 Sep 2026');
    });

    test('renders blank for a null or malformed value', () {
      expect(formatDate(null), '');
      expect(formatDate('garbage'), '');
    });
  });

  group('formatDateLong', () {
    test('renders day and full month, no year', () {
      expect(formatDateLong('2026-09-13'), '13 September');
    });
  });

  group('toWireDate / toWireDateTime round trip', () {
    test('toWireDate produces yyyy-MM-dd', () {
      final date = DateTime(2026, 9, 7);
      expect(toWireDate(date), '2026-09-07');
    });

    test('toWireDateTime carries the Colombo offset', () {
      final local = DateTime(2026, 9, 7, 16, 30);
      expect(toWireDateTime(local), endsWith('+05:30'));
      expect(toWireDateTime(local), startsWith('2026-09-07T16:30:00'));
    });
  });

  group('toCompanyTime', () {
    test('converts a UTC instant to Colombo local time (+5:30)', () {
      final utc = DateTime.utc(2026, 9, 8, 19, 0);
      final local = toCompanyTime(utc);
      // 19:00 UTC + 5:30 = 00:30 the next day.
      expect(local.hour, 0);
      expect(local.minute, 30);
      expect(local.day, 9);
    });
  });

  group('parseWireDateTime', () {
    test('parses an ISO datetime with an explicit offset', () {
      final parsed = parseWireDateTime('2026-09-07T16:30:00+05:30');
      expect(parsed, isNotNull);
      // Already in Colombo time — should stay put, not shift again.
      expect(parsed!.hour, 16);
      expect(parsed.minute, 30);
    });

    test('returns null for empty or malformed input', () {
      expect(parseWireDateTime(''), isNull);
      expect(parseWireDateTime('not-a-datetime'), isNull);
    });
  });
}
