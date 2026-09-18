import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:velmart/core/storage/secure_store.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/data/auth_repository.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/auth/presentation/more_screen.dart';

/// P7.12 — the Owner-only AI entry point must be *absent* for a manager
/// (never greyed out), and present for an Owner. `AuthController` calls
/// `fetchMe()` in its constructor, so a fake `AuthRepository` resolves it
/// immediately rather than mocking Dio's HTTP layer for a plain role check.
class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository(this._user) : super(dio: Dio(), secureStore: SecureStore());

  final User _user;

  @override
  Future<User> fetchMe() async => _user;
}

User _userWithRole(UserRole role) => User(
  id: 'user-1',
  companyId: 'company-1',
  fullName: 'Test User',
  email: 'test@velmart.lk',
  role: role,
  storeIds: const [],
);

Widget _pumpableFor(UserRole role) {
  return ProviderScope(
    overrides: [
      authRepositoryProvider.overrideWithValue(_FakeAuthRepository(_userWithRole(role))),
    ],
    child: const MaterialApp(home: MoreScreen()),
  );
}

void main() {
  testWidgets('More does not host AI — it is an Owner tab, not a More item', (tester) async {
    await tester.pumpWidget(_pumpableFor(UserRole.owner));
    await tester.pumpAndSettle();

    expect(find.text('Ask about your business'), findsNothing);
    expect(find.text('Reconciliation'), findsOneWidget);
    expect(find.text('Audit log'), findsOneWidget);
    expect(find.text('Owner'), findsOneWidget);
    expect(find.text('LKR'), findsOneWidget);
    expect(find.text('Asia/Colombo'), findsOneWidget);
    expect(find.text(r'$3.00'), findsOneWidget);
    expect(find.text('Users'), findsOneWidget);
    expect(find.text('Create managers and change roles'), findsOneWidget);
  });

  testWidgets('a Manager has no AI entry point on More', (tester) async {
    await tester.pumpWidget(_pumpableFor(UserRole.manager));
    await tester.pumpAndSettle();

    expect(find.text('Ask about your business'), findsNothing);
    expect(find.text('Reconciliation'), findsOneWidget);
    expect(find.text(r'$3.00'), findsNothing);
    expect(find.text('Assistant daily limit'), findsNothing);
    expect(find.text('Users'), findsNothing);
    expect(find.text('Create managers and change roles'), findsNothing);
  });
}
