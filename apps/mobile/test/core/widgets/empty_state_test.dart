import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/empty_state.dart';

void main() {
  Widget pumpable(Widget child) => MaterialApp(home: Scaffold(body: child));

  testWidgets('the default constructor shows the given message and action', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      pumpable(
        EmptyState(
          title: 'No records yet',
          message: 'Add the first one.',
          actionLabel: 'Add record',
          onAction: () => tapped = true,
        ),
      ),
    );

    expect(find.text('No records yet'), findsOneWidget);
    expect(find.text('Add the first one.'), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Add record'));
    expect(tapped, isTrue);
  });

  group('EmptyState.filtered', () {
    testWidgets('falls back to the generic try-a-different-value copy without a total', (
      tester,
    ) async {
      await tester.pumpWidget(pumpable(EmptyState.filtered(onClear: () {})));

      expect(find.text('No records match these filters'), findsOneWidget);
      expect(
        find.text('Try a different value, or clear the filters to see every record on this page.'),
        findsOneWidget,
      );
      expect(find.widgetWithText(FilledButton, 'Clear filters'), findsOneWidget);
    });

    testWidgets('shows the remaining total when one is given', (tester) async {
      await tester.pumpWidget(pumpable(EmptyState.filtered(totalCount: 1284, onClear: () {})));

      expect(find.text('The page still has 1284 records.'), findsOneWidget);
    });

    testWidgets('Clear filters calls onClear exactly once', (tester) async {
      var calls = 0;
      await tester.pumpWidget(pumpable(EmptyState.filtered(onClear: () => calls++)));

      await tester.tap(find.widgetWithText(FilledButton, 'Clear filters'));
      expect(calls, 1);
    });
  });
}
