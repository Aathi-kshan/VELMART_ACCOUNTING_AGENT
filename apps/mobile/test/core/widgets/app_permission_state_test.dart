import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/app_permission_state.dart';

void main() {
  testWidgets('shows the permission-denied copy and calls onGoBack', (tester) async {
    var tapped = false;
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: AppPermissionState(onGoBack: () => tapped = true)),
      ),
    );

    expect(find.text("You don't have permission to do that"), findsOneWidget);
    expect(find.text('Ask the Owner if you need access to this page.'), findsOneWidget);

    await tester.tap(find.widgetWithText(FilledButton, 'Go back'));
    expect(tapped, isTrue);
  });

  testWidgets('no action button when onGoBack is omitted', (tester) async {
    await tester.pumpWidget(const MaterialApp(home: Scaffold(body: AppPermissionState())));

    expect(find.byType(FilledButton), findsNothing);
  });
}
