import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/pages/domain/column.dart';
import 'package:velmart/features/pages/presentation/record_list_screen.dart';

void main() {
  PageColumn col(ColumnType type) => PageColumn(
    id: 'c',
    pageId: 'p',
    key: 'field',
    name: 'Field',
    dataType: type,
    position: 0,
    isRequired: false,
    isIndexed: false,
    isProtected: false,
    config: const {},
    isArchived: false,
  );

  test('formats money and dates instead of wire strings', () {
    expect(formatRecordValue(col(ColumnType.currency), '250000.00'), 'Rs. 250,000');
    expect(formatRecordValue(col(ColumnType.date), '2026-09-16'), '16 Sep 2026');
    expect(formatRecordValue(col(ColumnType.select), 'PENDING'), 'Pending');
    expect(formatRecordValue(col(ColumnType.boolean), true), 'Yes');
    expect(formatRecordValue(col(ColumnType.text), null), '—');
  });
}
