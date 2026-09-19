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

// `POST /records/{id}/reverse` has existed since P4 and the client already
// rendered the resulting REVERSED status — but nothing could ever *trigger* a
// reversal, so correcting a ledger entry was impossible from the app. A
// LEDGER page also rejects PATCH on the server, so reversal is not one way to
// correct an entry, it is the only way.
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

  const manager = User(
    id: 'manager-1',
    companyId: 'company-1',
    fullName: 'Demo Manager',
    email: 'manager@test.lk',
    role: UserRole.manager,
    storeIds: [],
  );

  const ledgerRecord = PageRecord(
    id: 'record-1',
    companyId: 'company-1',
    pageId: 'page-ledger',
    occurredAt: '2026-09-13T10:00:00+05:30',
    businessDate: '2026-09-13',
    status: RecordStatus.active,
    data: {'amount': '100.00'},
    needsReview: false,
    version: 3,
    createdBy: 'owner-1',
  );

  PageSchema schemaOfKind(PageKind kind) => PageSchema(
    page: Page(
      id: 'page-ledger',
      companyId: 'company-1',
      key: 'cash_movements',
      name: 'Cash Movements',
      kind: kind,
      isArchived: false,
      isSystem: false,
      version: 1,
    ),
    columns: const [
      PageColumn(
        id: 'col-1',
        pageId: 'page-ledger',
        key: 'amount',
        name: 'Amount',
        dataType: ColumnType.currency,
        position: 0,
        isRequired: true,
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
    when(
      () => mockRepository.queryRecords(any(), any()),
    ).thenAnswer((_) async => const Paginated(items: [ledgerRecord]));
  });

  Widget pumpable({
    required User user,
    required PageSchema schema,
    PageRecord record = ledgerRecord,
  }) {
    when(() => mockAuthRepository.fetchMe()).thenAnswer((_) async => user);
    // The confirm dialog dismisses through go_router's `context.pop()`, so a
    // real GoRouter ancestor is required — same reason the delete test uses one.
    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(
          path: '/',
          builder: (context, state) => Scaffold(
            body: RecordDetailView(record: record, schema: schema),
          ),
        ),
      ],
    );
    return ProviderScope(
      overrides: [
        pageRepositoryProvider.overrideWithValue(mockRepository),
        authControllerProvider.overrideWith(
          (ref) => AuthController(mockAuthRepository),
        ),
      ],
      child: MaterialApp.router(routerConfig: router),
    );
  }

  testWidgets('an Owner can reverse an active ledger entry', (tester) async {
    when(
      () => mockRepository.reverseRecord(any(), version: any(named: 'version')),
    ).thenAnswer((_) async => ledgerRecord);

    await tester.pumpWidget(
      pumpable(user: owner, schema: schemaOfKind(PageKind.ledger)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Reverse this entry'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Reverse entry'));
    await tester.pumpAndSettle();

    // The record's own version goes up as `If-Match`, so a concurrent edit
    // makes the server refuse rather than reverse something else.
    verify(() => mockRepository.reverseRecord('record-1', version: 3)).called(1);
  });

  testWidgets('cancelling reverses nothing', (tester) async {
    await tester.pumpWidget(
      pumpable(user: owner, schema: schemaOfKind(PageKind.ledger)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.widgetWithText(OutlinedButton, 'Reverse this entry'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(TextButton, 'Cancel'));
    await tester.pumpAndSettle();

    verifyNever(
      () => mockRepository.reverseRecord(any(), version: any(named: 'version')),
    );
  });

  testWidgets('the action refreshes the page\'s record list', (tester) async {
    when(
      () => mockRepository.reverseRecord(any(), version: any(named: 'version')),
    ).thenAnswer((_) async => ledgerRecord);

    await tester.pumpWidget(
      pumpable(user: owner, schema: schemaOfKind(PageKind.ledger)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(OutlinedButton, 'Reverse this entry'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Reverse entry'));
    await tester.pumpAndSettle();

    // A reversal changes what the list should show — the reversed row stops
    // counting towards totals — so the list has to refetch, exactly as the
    // delete path does.
    verify(() => mockRepository.queryRecords('page-ledger', any())).called(2);
  });

  testWidgets('a register page offers no reversal', (tester) async {
    // Reversal is a ledger concept; the server rejects it on a REGISTER page,
    // so the button must not be offered there.
    await tester.pumpWidget(
      pumpable(user: owner, schema: schemaOfKind(PageKind.register)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Reverse this entry'), findsNothing);
  });

  testWidgets('a Manager is not offered reversal', (tester) async {
    await tester.pumpWidget(
      pumpable(user: manager, schema: schemaOfKind(PageKind.ledger)),
    );
    await tester.pumpAndSettle();

    expect(find.text('Reverse this entry'), findsNothing);
  });

  testWidgets('an already-reversed entry cannot be reversed again', (
    tester,
  ) async {
    const reversed = PageRecord(
      id: 'record-1',
      companyId: 'company-1',
      pageId: 'page-ledger',
      occurredAt: '2026-09-13T10:00:00+05:30',
      businessDate: '2026-09-13',
      status: RecordStatus.reversed,
      data: {'amount': '100.00'},
      needsReview: false,
      version: 4,
      createdBy: 'owner-1',
    );

    await tester.pumpWidget(
      pumpable(
        user: owner,
        schema: schemaOfKind(PageKind.ledger),
        record: reversed,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Reverse this entry'), findsNothing);
  });
}
