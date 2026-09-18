import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/app_conflict_state.dart';

void main() {
  const title = 'This record changed since you opened it';
  const message = "Your edits weren't saved. Reload to see the latest values.";

  testWidgets('the full-screen state shows the conflict copy and calls onReload', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: AppConflictState(onReload: () => tapped = true)),
      ),
    );

    expect(find.text(title), findsOneWidget);
    expect(find.text(message), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Reload latest'));
    expect(tapped, isTrue);
  });

  testWidgets('presentDialog shows the same copy and closes after calling onReload', (
    tester,
  ) async {
    var reloaded = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () =>
                  AppConflictState.presentDialog(context, onReload: () => reloaded = true),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();
    expect(find.text(title), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Reload latest'));
    await tester.pumpAndSettle();

    expect(reloaded, isTrue);
    expect(find.text(title), findsNothing);
  });
}
