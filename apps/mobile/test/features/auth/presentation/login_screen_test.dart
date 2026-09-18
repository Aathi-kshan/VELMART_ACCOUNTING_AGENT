import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/storage/secure_store.dart';
import 'package:velmart/core/widgets/velmart_logo.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/data/auth_repository.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/auth/presentation/login_screen.dart';

class _UnauthenticatedRepository extends AuthRepository {
  _UnauthenticatedRepository() : super(dio: Dio(), secureStore: SecureStore());

  @override
  Future<User> fetchMe() async => throw Exception('no session');
}

void main() {
  testWidgets('session restore does not spin the Sign in button', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(_UnauthenticatedRepository()),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pump();

    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    expect(find.byType(CircularProgressIndicator), findsNothing);
  });

  testWidgets('login shows the Velmart mark, fields, and inactivity copy', (tester) async {
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(_UnauthenticatedRepository()),
        ],
        child: const MaterialApp(home: LoginScreen()),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(VelmartLogo), findsOneWidget);
    expect(find.text('Velmart'), findsOneWidget);
    expect(find.text('Business data and accounting'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Email'), findsOneWidget);
    expect(find.widgetWithText(TextFormField, 'Password'), findsOneWidget);
    expect(find.widgetWithText(FilledButton, 'Sign in'), findsOneWidget);
    expect(find.text('Signed-out after 15 minutes of inactivity.'), findsOneWidget);
  });
}
