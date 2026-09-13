/// Dates on the wire and on screen (plan section 9.2).
///
/// Four timestamps, each with a job:
///
///     occurred_at    when the business event happened      TIMESTAMPTZ
///     business_date  the accounting day it belongs to      DATE
///     created_at     when it was entered into the system   TIMESTAMPTZ
///     updated_at     when it was last changed              TIMESTAMPTZ
///
/// **The client never computes `business_date`.** It is derived server-side
/// from the page's designated date column or from `occurred_at` plus the
/// company's `day_cutoff_hour` — a shop closing at 11pm and cashing up at
/// 12:30am posts to the previous business day, and only the server knows the
/// cutoff. This file parses and renders; it never decides.
///
/// Everything is stored in UTC and rendered in Asia/Colombo. Sri Lanka is
/// UTC+5:30 year round with no DST, so a fixed offset is correct here and
/// avoids pulling in a full timezone database.
library;

import 'package:intl/intl.dart';

/// Asia/Colombo — fixed, no DST (plan section 9.2).
const Duration colomboOffset = Duration(hours: 5, minutes: 30);

final DateFormat _displayDate = DateFormat('d MMM yyyy');
final DateFormat _displayDateTime = DateFormat('d MMM yyyy, h:mm a');
final DateFormat _wireDate = DateFormat('yyyy-MM-dd');

/// Parse a wire `DATE` (`"2026-09-07"`) into a date-only `DateTime`.
///
/// Returns null rather than throwing: a malformed value in stored JSONB
/// should render as blank, not crash the record list.
DateTime? parseWireDate(Object? value) {
  if (value is DateTime) return value;
  if (value is! String || value.isEmpty) return null;
  return DateTime.tryParse(value);
}

/// Parse a wire `DATETIME` (`"2026-09-07T16:30:00+05:30"`) and convert it to
/// the company's local wall clock, which is what the shopkeeper means.
DateTime? parseWireDateTime(Object? value) {
  if (value is DateTime) return toCompanyTime(value);
  if (value is! String || value.isEmpty) return null;
  final parsed = DateTime.tryParse(value);
  return parsed == null ? null : toCompanyTime(parsed);
}

/// A UTC (or offset-bearing) instant rendered on the Colombo wall clock.
DateTime toCompanyTime(DateTime moment) => moment.toUtc().add(colomboOffset);

/// Format a `DATE` column value for display: `7 Sep 2026`.
String formatDate(Object? value) {
  final parsed = parseWireDate(value);
  return parsed == null ? '' : _displayDate.format(parsed);
}

/// Format a `DATETIME` column value for display: `7 Sep 2026, 4:30 PM`.
String formatDateTime(Object? value) {
  final parsed = parseWireDateTime(value);
  return parsed == null ? '' : _displayDateTime.format(parsed);
}

/// The wire format for a `DATE` column: `yyyy-MM-dd`, no time, no zone.
String toWireDate(DateTime value) => _wireDate.format(value);

/// The wire format for `DATETIME` and `occurred_at`: ISO 8601 carrying the
/// Colombo offset, e.g. `2026-09-07T16:30:00.000+05:30`.
///
/// The server needs the offset to place the instant correctly; sending a bare
/// local time would let it be read as UTC and shift the business date by
/// five and a half hours.
String toWireDateTime(DateTime value) {
  final local = value.isUtc ? toCompanyTime(value) : value;
  final stamp = local.toIso8601String().split('.').first;
  return '$stamp.000+05:30';
}

/// `occurred_at` for a record being entered right now.
String nowOccurredAt() => toWireDateTime(toCompanyTime(DateTime.now().toUtc()));
