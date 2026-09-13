import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/pages/domain/column.dart';
import 'package:velmart/features/pages/presentation/widgets/field_renderers/field_renderer.dart';

// The dispatcher this whole client is built around (plan section 3.12) — a
// silent mis-dispatch here means one column type renders as the wrong
// widget on every page an Owner ever builds with it.
void main() {
  PageColumn column({
    required ColumnType dataType,
    bool isRequired = false,
    bool isProtected = false,
    Map<String, dynamic> config = const {},
  }) {
    return PageColumn(
      id: 'col-1',
      pageId: 'page-1',
      key: 'field',
      name: 'Field',
      dataType: dataType,
      position: 0,
      isRequired: isRequired,
      isIndexed: false,
      isProtected: isProtected,
      config: config,
      isArchived: false,
    );
  }

  Widget pumpable({
    required PageColumn column,
    Object? value,
    ValueChanged<Object?>? onChanged,
    UserRole role = UserRole.owner,
  }) {
    return MaterialApp(
      home: Scaffold(
        body: Form(
          child: FieldRenderer(
            column: column,
            value: value,
            role: role,
            onChanged: onChanged ?? (_) {},
          ),
        ),
      ),
    );
  }

  testWidgets('TEXT dispatches to a text field', (tester) async {
    await tester.pumpWidget(pumpable(column: column(dataType: ColumnType.text), value: 'hello'));
    expect(find.byType(TextFormField), findsOneWidget);
    expect(find.text('hello'), findsOneWidget);
  });

  testWidgets('CURRENCY dispatches to a text field with an Rs. prefix', (tester) async {
    await tester.pumpWidget(
      pumpable(column: column(dataType: ColumnType.currency), value: '5000.00'),
    );
    expect(find.byType(TextFormField), findsOneWidget);
    expect(find.text('Rs. '), findsOneWidget);
  });

  testWidgets('BOOLEAN dispatches to a switch', (tester) async {
    await tester.pumpWidget(pumpable(column: column(dataType: ColumnType.boolean), value: true));
    expect(find.byType(SwitchListTile), findsOneWidget);
    final switchTile = tester.widget<SwitchListTile>(find.byType(SwitchListTile));
    expect(switchTile.value, isTrue);
  });

  testWidgets('SELECT dispatches to a dropdown with the configured options', (tester) async {
    await tester.pumpWidget(
      pumpable(
        column: column(
          dataType: ColumnType.select,
          config: {'options': ['Electricity', 'Rent']},
        ),
        value: 'Electricity',
      ),
    );
    expect(find.byType(DropdownButtonFormField<String>), findsOneWidget);
  });

  testWidgets('MULTI_SELECT dispatches to filter chips', (tester) async {
    await tester.pumpWidget(
      pumpable(
        column: column(
          dataType: ColumnType.multiSelect,
          config: {'options': ['Urgent', 'Repair']},
        ),
        value: ['Urgent'],
      ),
    );
    expect(find.byType(FilterChip), findsNWidgets(2));
    final urgentChip = tester.widget<FilterChip>(
      find.ancestor(of: find.text('Urgent'), matching: find.byType(FilterChip)),
    );
    expect(urgentChip.selected, isTrue);
  });

  testWidgets('a protected SELECT is locked for a manager', (tester) async {
    await tester.pumpWidget(
      pumpable(
        column: column(
          dataType: ColumnType.select,
          isProtected: true,
          config: {'options': ['PENDING', 'PAID'], 'default': 'PENDING'},
        ),
        value: 'PENDING',
        role: UserRole.manager,
      ),
    );
    final dropdown = tester.widget<DropdownButtonFormField<String>>(
      find.byType(DropdownButtonFormField<String>),
    );
    expect(dropdown.onChanged, isNull);
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);
  });

  testWidgets('a protected SELECT is locked for an owner too', (tester) async {
    // P4: no one changes a protected value through the generic form any
    // more, owner included — only the dedicated protected-field action on
    // the record detail screen does.
    await tester.pumpWidget(
      pumpable(
        column: column(
          dataType: ColumnType.select,
          isProtected: true,
          config: {'options': ['PENDING', 'PAID']},
        ),
        value: 'PENDING',
        role: UserRole.owner,
      ),
    );
    final dropdown = tester.widget<DropdownButtonFormField<String>>(
      find.byType(DropdownButtonFormField<String>),
    );
    expect(dropdown.onChanged, isNull);
    expect(find.byIcon(Icons.lock_outline), findsOneWidget);
  });

  testWidgets('FORMULA renders read-only regardless of role', (tester) async {
    await tester.pumpWidget(
      pumpable(column: column(dataType: ColumnType.formula), value: null, role: UserRole.owner),
    );
    final field = tester.widget<TextFormField>(find.byType(TextFormField));
    expect(field.enabled, isFalse);
    expect(find.byIcon(Icons.functions), findsOneWidget);
  });

  testWidgets('ATTACHMENT renders a read-only count', (tester) async {
    await tester.pumpWidget(pumpable(column: column(dataType: ColumnType.attachment), value: 3));
    expect(find.text('3 attachments'), findsOneWidget);
  });

  testWidgets('editing a TEXT field calls onChanged with the new value', (tester) async {
    Object? received;
    await tester.pumpWidget(
      pumpable(
        column: column(dataType: ColumnType.text),
        value: '',
        onChanged: (next) => received = next,
      ),
    );
    await tester.enterText(find.byType(TextFormField), 'new value');
    expect(received, 'new value');
  });
}
