import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/data/auth_repository.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/pages/application/pages_providers.dart';
import 'package:velmart/features/pages/data/page_repository.dart';
import 'package:velmart/features/pages/domain/column.dart';
import 'package:velmart/features/pages/domain/page.dart';
import 'package:velmart/features/pages/domain/record.dart';
import 'package:velmart/features/pages/presentation/record_detail_screen.dart';

class MockPageRepository extends Mock implements PageRepository {}

class MockAuthRepository extends Mock implements AuthRepository {}

// Regression test for a real bug: unlike record_form_screen.dart's create/
// update path, deleting a record never refreshed the page's own record
// list — the deleted row stayed visible until something else happened to
// refetch it, making a successful delete look like it silently did nothing.
void main() {
  setUpAll(() {
    registerFallbackValue(const RecordQuery());
  });

  const owner = User(
    id: 'owner-1',
    companyId: 'company-1',
    fullName: 'Demo Owner',
    email: 'owner@test.lk',
    role: UserRole.owner,
    storeIds: [],
  );

  const record = PageRecord(
    id: 'record-1',
    companyId: 'company-1',
    pageId: 'page-1',
    occurredAt: '2026-09-13T10:00:00+05:30',
    businessDate: '2026-09-13',
    status: RecordStatus.active,
    data: {'note': 'hello'},
    needsReview: false,
    version: 1,
    createdBy: 'owner-1',
  );

  const schema = PageSchema(
    page: Page(
      id: 'page-1',
      companyId: 'company-1',
      key: 'notes',
      name: 'Notes',
      kind: PageKind.register,
      isArchived: false,
      isSystem: false,
      version: 1,
    ),
    columns: [
      PageColumn(
        id: 'col-1',
        pageId: 'page-1',
        key: 'note',
        name: 'Note',
        dataType: ColumnType.text,
        position: 0,
        isRequired: false,
        isIndexed: false,
        isProtected: false,
        config: {},
        isArchived: false,
      ),
    ],
  );

  late MockPageRepository mockRepository;
  late MockAuthRepository mockAuthRepository;

  setUp(() {
    mockRepository = MockPageRepository();
    mockAuthRepository = MockAuthRepository();
    when(() => mockAuthRepository.fetchMe()).thenAnswer((_) async => owner);
    when(
      () => mockRepository.queryRecords(any(), any()),
    ).thenAnswer((_) async => const Paginated(items: [record]));
  });

  Widget pumpable() {
    // `_confirmDelete`'s dialog dismisses via go_router's `context.pop()`
    // (`GoRouterHelper`, not a plain `Navigator.pop()`), so this needs a
    // real (if minimal) `GoRouter` ancestor rather than a plain `MaterialApp`
    // — the same reason record_form_screen/record_list_screen stay untested
    // at the widget level (see the P3 client's own notes on that).
    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) =>
              const Scaffold(body: RecordDetailView(record: record, schema: schema)),
        ),
      ],
    );
    return ProviderScope(
      overrides: [
        pageRepositoryProvider.overrideWithValue(mockRepository),
        authControllerProvider.overrideWith((ref) => AuthController(mockAuthRepository)),
      ],
      child: MaterialApp.router(routerConfig: router),
    );
  }

  testWidgets('deleting a record refreshes that page\'s record list', (tester) async {
    when(
      () => mockRepository.deleteRecord(any(), reason: any(named: 'reason')),
    ).thenAnswer((_) async {});

    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Delete'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'no longer needed');
    await tester.tap(find.widgetWithText(FilledButton, 'Delete'));
    await tester.pumpAndSettle();

    verify(() => mockRepository.deleteRecord(record.id, reason: 'no longer needed')).called(1);
    // Once from `recordListControllerProvider`'s own construction (lazily
    // triggered the moment `_confirmDelete` first reads it), once more from
    // the explicit `.refresh()` call this fix adds — exactly 2, not 1.
    verify(() => mockRepository.queryRecords(record.pageId, any())).called(2);
  });
}
