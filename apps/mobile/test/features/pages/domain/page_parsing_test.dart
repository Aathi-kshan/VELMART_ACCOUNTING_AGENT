import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/pages/domain/column.dart';
import 'package:velmart/features/pages/domain/page.dart';
import 'package:velmart/features/pages/domain/record.dart';

// Mirrors apps/api/tests/test_page_engine.py and test_record_validation.py —
// the client-side half of parsing what the server actually sends. This is
// where a silent wire-format mismatch (a renamed field, a type the server
// added) would otherwise go unnoticed until a real device hits it.
void main() {
  group('ColumnType.fromWire', () {
    const wireValues = [
      'TEXT',
      'LONG_TEXT',
      'NUMBER',
      'CURRENCY',
      'PERCENT',
      'DATE',
      'DATETIME',
      'BOOLEAN',
      'SELECT',
      'MULTI_SELECT',
      'RECORD_REF',
      'STORE_REF',
      'USER_REF',
      'FORMULA',
      'ATTACHMENT',
    ];

    test('round-trips every one of the 15 column types', () {
      for (final wire in wireValues) {
        final type = ColumnType.fromWire(wire);
        expect(type.wire, wire, reason: 'wire mismatch for $wire');
      }
    });

    test('rejects an unknown type rather than defaulting silently', () {
      expect(() => ColumnType.fromWire('NOT_A_TYPE'), throwsArgumentError);
    });

    test('FORMULA and ATTACHMENT are read-only; nothing else is', () {
      for (final type in ColumnType.values) {
        final expected = type == ColumnType.formula || type == ColumnType.attachment;
        expect(type.isReadOnly, expected, reason: '$type.isReadOnly');
      }
    });

    test('only NUMBER, CURRENCY, DATE, DATETIME are indexable', () {
      const expectedIndexable = {
        ColumnType.number,
        ColumnType.currency,
        ColumnType.date,
        ColumnType.datetime,
      };
      for (final type in ColumnType.values) {
        expect(type.isIndexable, expectedIndexable.contains(type), reason: '$type.isIndexable');
      }
    });

    test('only SELECT supports protection', () {
      for (final type in ColumnType.values) {
        expect(type.supportsProtection, type == ColumnType.select, reason: '$type');
      }
    });
  });

  group('PageColumn.fromJson', () {
    Map<String, dynamic> baseJson({Map<String, dynamic>? config}) => {
      'id': 'col-1',
      'page_id': 'page-1',
      'key': 'amount',
      'name': 'Amount',
      'data_type': 'CURRENCY',
      'position': 0,
      'is_required': true,
      'is_indexed': true,
      'is_protected': false,
      'config': config ?? {'min': 0, 'allow_negative': false},
      'description': null,
      'is_archived': false,
    };

    test('parses required fields', () {
      final column = PageColumn.fromJson(baseJson());
      expect(column.key, 'amount');
      expect(column.dataType, ColumnType.currency);
      expect(column.isRequired, true);
      expect(column.isIndexed, true);
    });

    test('defaults config to an empty map when absent', () {
      final json = baseJson()..remove('config');
      final column = PageColumn.fromJson(json);
      expect(column.config, isEmpty);
    });

    test('exposes SELECT options through the typed accessor', () {
      final column = PageColumn.fromJson(
        baseJson(config: {'options': ['Electricity', 'Rent'], 'default': 'Electricity'}),
      );
      expect(column.options, ['Electricity', 'Rent']);
      expect(column.defaultValue, 'Electricity');
    });

    test('exposes numeric bounds as strings, never doubles', () {
      final column = PageColumn.fromJson(baseJson(config: {'min': 0, 'max': '100.50'}));
      expect(column.minValue, '0');
      expect(column.maxValue, '100.50');
    });

    test('exposes RECORD_REF target and display column', () {
      final column = PageColumn.fromJson(
        baseJson(
          config: {'target_page_key': 'suppliers', 'display_column': 'name'},
        )..['data_type'] = 'RECORD_REF',
      );
      expect(column.targetPageKey, 'suppliers');
      expect(column.displayColumn, 'name');
    });
  });

  group('PageSchema.fromJson', () {
    test('sorts columns by position and filters nothing else', () {
      final schema = PageSchema.fromJson({
        'id': 'page-1',
        'company_id': 'company-1',
        'key': 'expenses_log',
        'name': 'Expenses Log',
        'kind': 'REGISTER',
        'description': null,
        'icon': null,
        'date_column_key': null,
        'store_column_key': null,
        'is_archived': false,
        'is_system': false,
        'storage_table': null,
        'version': 1,
        'columns': [
          {
            'id': 'c2',
            'page_id': 'page-1',
            'key': 'amount',
            'name': 'Amount',
            'data_type': 'CURRENCY',
            'position': 1,
            'is_required': true,
            'is_indexed': false,
            'is_protected': false,
            'config': <String, dynamic>{},
            'description': null,
            'is_archived': false,
          },
          {
            'id': 'c1',
            'page_id': 'page-1',
            'key': 'note',
            'name': 'Note',
            'data_type': 'TEXT',
            'position': 0,
            'is_required': false,
            'is_indexed': false,
            'is_protected': false,
            'config': <String, dynamic>{},
            'description': null,
            'is_archived': false,
          },
        ],
      });

      expect(schema.columns.map((c) => c.key), ['note', 'amount']);
      expect(schema.page.key, 'expenses_log');
      expect(schema.writableColumns.length, 2);
      expect(schema.columnByKey('amount')?.dataType, ColumnType.currency);
      expect(schema.columnByKey('missing'), isNull);
      // TEXT is preferred as the display column when one exists.
      expect(schema.displayColumn?.key, 'note');
    });
  });

  group('PageRecord.fromJson', () {
    test('parses platform fields and keeps data in wire format', () {
      final record = PageRecord.fromJson({
        'id': 'rec-1',
        'company_id': 'company-1',
        'page_id': 'page-1',
        'store_id': null,
        'occurred_at': '2026-09-07T16:30:00+05:30',
        'business_date': '2026-09-07',
        'status': 'ACTIVE',
        'data': {'amount': '50000.00', 'category': 'Electricity'},
        'needs_review': false,
        'version': 1,
        'created_by': 'user-1',
        'updated_by': null,
      });

      expect(record.status, RecordStatus.active);
      expect(record.businessDate, '2026-09-07');
      // The stored value stays a string — nothing here parses it into a
      // Decimal/double (plan section 9.1).
      expect(record.data['amount'], isA<String>());
      expect(record.data['amount'], '50000.00');
    });

    test('round-trips every record status', () {
      for (final status in RecordStatus.values) {
        final wire = switch (status) {
          RecordStatus.active => 'ACTIVE',
          RecordStatus.reversed => 'REVERSED',
          RecordStatus.void_ => 'VOID',
        };
        expect(RecordStatus.fromWire(wire), status);
      }
    });
  });

  group('Paginated.fromJson', () {
    test('parses items, cursor, and has_more', () {
      final page = Paginated.fromJson(
        {
          'items': [
            {'id': '1'},
            {'id': '2'},
          ],
          'next_cursor': 'abc123',
          'has_more': true,
        },
        (json) => json['id'] as String,
      );
      expect(page.items, ['1', '2']);
      expect(page.nextCursor, 'abc123');
      expect(page.hasMore, true);
    });

    test('defaults has_more to false and cursor to null when absent', () {
      final page = Paginated.fromJson({'items': []}, (json) => json['id'] as String);
      expect(page.hasMore, false);
      expect(page.nextCursor, isNull);
    });
  });

  group('FilterOp.forType', () {
    test('FORMULA and ATTACHMENT accept no filter operators', () {
      expect(FilterOp.forType(ColumnType.formula), isEmpty);
      expect(FilterOp.forType(ColumnType.attachment), isEmpty);
    });

    test('BOOLEAN only offers eq and is_null', () {
      expect(FilterOp.forType(ColumnType.boolean), [FilterOp.eq, FilterOp.isNull]);
    });

    test('CURRENCY supports the full ordering set plus between', () {
      final ops = FilterOp.forType(ColumnType.currency);
      expect(ops, contains(FilterOp.between));
      expect(ops, contains(FilterOp.gte));
    });
  });

  group('RecordQuery', () {
    test('toJson omits empty search and cursor', () {
      const query = RecordQuery();
      final json = query.toJson();
      expect(json.containsKey('search'), isFalse);
      expect(json.containsKey('cursor'), isFalse);
      expect(json['limit'], 50);
    });

    test('sameShapeAs ignores the cursor', () {
      const a = RecordQuery(cursor: 'abc', search: 'x');
      const b = RecordQuery(cursor: 'def', search: 'x');
      const c = RecordQuery(cursor: 'abc', search: 'y');
      expect(a.sameShapeAs(b), isTrue);
      expect(a.sameShapeAs(c), isFalse);
    });
  });
}
