import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/amount_text.dart';

void main() {
  Widget pump(Object? value) {
    return MaterialApp(home: Scaffold(body: AmountText(value)));
  }

  testWidgets('omits cents for whole rupees', (tester) async {
    await tester.pumpWidget(pump('250000.00'));
    expect(find.text('Rs. 250,000'), findsOneWidget);
  });

  testWidgets('keeps cents when they are non-zero', (tester) async {
    await tester.pumpWidget(pump('250000.50'));
    expect(find.text('Rs. 250,000.50'), findsOneWidget);
  });
}
