import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/widgets/velmart_logo.dart';

void main() {
  testWidgets('full logo shows the V mark, wordmark, and tagline', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(body: VelmartLogo(variant: VelmartLogoVariant.full)),
      ),
    );

    expect(find.text('V'), findsOneWidget);
    expect(find.text('Velmart'), findsOneWidget);
    expect(find.text('Business data and accounting'), findsOneWidget);
  });
}
