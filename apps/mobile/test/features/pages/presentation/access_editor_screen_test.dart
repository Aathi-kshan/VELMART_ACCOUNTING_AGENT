import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/pages/application/pages_providers.dart';
import 'package:velmart/features/pages/data/page_repository.dart';
import 'package:velmart/features/pages/domain/page.dart';
import 'package:velmart/features/pages/presentation/access_editor_screen.dart';

class MockPageRepository extends Mock implements PageRepository {}

// Regression test for a real bug: the editor used to start every manager
// unchecked (there was no `GET /pages/{id}/access` to hydrate from), so an
// Owner who opened it to check on access and hit Save would silently wipe
// out every existing grant. This proves an already-granted manager shows up
// pre-checked, matching the real server state.
void main() {
  const manager = User(
    id: 'manager-1',
    companyId: 'company-1',
    fullName: 'Kamal',
    email: 'kamal@test.lk',
    role: UserRole.manager,
    storeIds: [],
  );

  late MockPageRepository mockRepository;

  setUp(() {
    mockRepository = MockPageRepository();
    when(() => mockRepository.listUsers()).thenAnswer((_) async => const [manager]);
  });

  Widget pumpable() {
    return ProviderScope(
      overrides: [pageRepositoryProvider.overrideWithValue(mockRepository)],
      child: const MaterialApp(home: AccessEditorScreen(pageId: 'page-1')),
    );
  }

  testWidgets('an already-granted manager is shown pre-checked', (tester) async {
    when(() => mockRepository.getAccess('page-1')).thenAnswer(
      (_) async => const [AccessGrant(userId: 'manager-1', canView: true, canCreate: false)],
    );

    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    final canViewTile = tester.widget<CheckboxListTile>(
      find.widgetWithText(CheckboxListTile, 'Can view'),
    );
    expect(canViewTile.value, isTrue);
    final canCreateTile = tester.widget<CheckboxListTile>(
      find.widgetWithText(CheckboxListTile, 'Can add records'),
    );
    expect(canCreateTile.value, isFalse);
  });

  testWidgets('saving preserves the hydrated grant rather than dropping it', (tester) async {
    when(() => mockRepository.getAccess('page-1')).thenAnswer(
      (_) async => const [AccessGrant(userId: 'manager-1', canView: true, canCreate: true)],
    );
    when(
      () => mockRepository.setAccess('page-1', any()),
    ).thenAnswer((_) async => const [AccessGrant(userId: 'manager-1', canView: true, canCreate: true)]);

    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(FilledButton, 'Save access'));
    await tester.pumpAndSettle();

    final captured = verify(() => mockRepository.setAccess('page-1', captureAny())).captured;
    final grants = captured.single as List<AccessGrant>;
    expect(grants, hasLength(1));
    expect(grants.single.userId, 'manager-1');
    expect(grants.single.canView, isTrue);
    expect(grants.single.canCreate, isTrue);
  });

  testWidgets('a manager with no grant starts unchecked', (tester) async {
    when(() => mockRepository.getAccess('page-1')).thenAnswer((_) async => const []);

    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    final canViewTile = tester.widget<CheckboxListTile>(
      find.widgetWithText(CheckboxListTile, 'Can view'),
    );
    expect(canViewTile.value, isFalse);
  });
}
