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
import 'package:velmart/features/pages/presentation/record_list_screen.dart';

class MockPageRepository extends Mock implements PageRepository {}

class MockAuthRepository extends Mock implements AuthRepository {}

void main() {
  setUpAll(() {
    registerFallbackValue(const RecordQuery());
    registerFallbackValue(
      const AggregateQuery(metric: AggregateMetric.count),
    );
  });

  const owner = User(
    id: 'owner-1',
    companyId: 'company-1',
    fullName: 'Aathi',
    email: 'owner@test.lk',
    role: UserRole.owner,
    storeIds: [],
  );

  const manager = User(
    id: 'manager-1',
    companyId: 'company-1',
    fullName: 'Manager 1',
    email: 'manager@test.lk',
    role: UserRole.manager,
    storeIds: [],
  );

  const schema = PageSchema(
    page: Page(
      id: 'page-exp',
      companyId: 'company-1',
      key: 'expenses',
      name: 'Expenses',
      kind: PageKind.register,
      isArchived: false,
      isSystem: true,
      version: 1,
    ),
    columns: [
      PageColumn(
        id: 'c1',
        pageId: 'page-exp',
        key: 'expense_name',
        name: 'Expense name',
        dataType: ColumnType.text,
        position: 0,
        isRequired: true,
        isIndexed: false,
        isProtected: false,
        config: {},
        isArchived: false,
      ),
      PageColumn(
        id: 'c2',
        pageId: 'page-exp',
        key: 'description',
        name: 'Description',
        dataType: ColumnType.longText,
        position: 1,
        isRequired: false,
        isIndexed: false,
        isProtected: false,
        config: {},
        isArchived: false,
      ),
      PageColumn(
        id: 'c3',
        pageId: 'page-exp',
        key: 'amount',
        name: 'Amount',
        dataType: ColumnType.currency,
        position: 2,
        isRequired: true,
        isIndexed: false,
        isProtected: false,
        config: {},
        isArchived: false,
      ),
    ],
  );

  const record = PageRecord(
    id: 'record-1',
    companyId: 'company-1',
    pageId: 'page-exp',
    occurredAt: '2026-09-13T10:00:00+05:30',
    businessDate: '2026-09-13',
    status: RecordStatus.active,
    data: {
      'expense_name': 'Electricity',
      'description': 'CEB bill',
      'amount': '52400.00',
    },
    needsReview: false,
    version: 1,
    createdBy: 'owner-1',
  );

  late MockPageRepository mockRepository;
  late MockAuthRepository mockAuthRepository;

  setUp(() {
    mockRepository = MockPageRepository();
    mockAuthRepository = MockAuthRepository();
    when(() => mockRepository.getSchema(any())).thenAnswer((_) async => schema);
    when(
      () => mockRepository.queryRecords(any(), any()),
    ).thenAnswer((_) async => const Paginated(items: [record]));
    when(() => mockRepository.aggregate(any(), any())).thenAnswer(
      (_) async => const AggregateResult(value: '52400.00', recordCount: 1, groups: []),
    );
    when(() => mockRepository.listUsers()).thenAnswer((_) async => [owner, manager]);
  });

  Widget pumpable(
    User user, {
    PageSchema? pageSchema,
    PageRecord? pageRecord,
  }) {
    if (pageSchema != null) {
      when(() => mockRepository.getSchema(any())).thenAnswer((_) async => pageSchema);
    }
    if (pageRecord != null) {
      when(
        () => mockRepository.queryRecords(any(), any()),
      ).thenAnswer((_) async => Paginated(items: [pageRecord]));
    }
    when(() => mockAuthRepository.fetchMe()).thenAnswer((_) async => user);
    final router = GoRouter(
      initialLocation: '/pages/page-exp/records',
      routes: [
        GoRoute(
          path: '/pages/:pageId/records',
          builder: (context, state) =>
              RecordListScreen(pageId: state.pathParameters['pageId']!),
        ),
        GoRoute(
          path: '/pages/:pageId/records/new',
          name: 'recordNew',
          builder: (_, __) => const SizedBox(),
        ),
        GoRoute(
          path: '/records/:recordId',
          name: 'recordDetail',
          builder: (_, __) => const SizedBox(),
        ),
        GoRoute(
          path: '/records/:recordId/edit',
          name: 'recordEdit',
          builder: (_, __) => const SizedBox(),
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

  Future<void> setDesktop(WidgetTester tester) async {
    tester.view.physicalSize = const Size(1400, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('Owner desktop list matches prototype chrome and columns', (tester) async {
    await setDesktop(tester);
    await tester.pumpWidget(pumpable(owner));
    await tester.pumpAndSettle();

    expect(find.text('Expenses'), findsWidgets);
    expect(find.text('Search'), findsOneWidget);
    expect(find.text('Filter'), findsOneWidget);
    expect(find.text('Add record'), findsOneWidget);
    expect(find.text('Date'), findsOneWidget);
    expect(find.text('Expense name'), findsOneWidget);
    expect(find.text('Description'), findsOneWidget);
    expect(find.text('Amount'), findsOneWidget);
    expect(find.text('Entered by'), findsOneWidget);
    expect(find.text('13 Sep 2026'), findsOneWidget);
    expect(find.text('Electricity'), findsOneWidget);
    expect(find.text('Aathi'), findsOneWidget);
    expect(find.text('CEB bill'), findsOneWidget);
    expect(find.text('Rs. 52,400'), findsOneWidget);
    expect(find.textContaining('1 record'), findsOneWidget);
  });

  testWidgets('Manager desktop list has add record but no row action icons', (tester) async {
    await setDesktop(tester);
    await tester.pumpWidget(pumpable(manager));
    await tester.pumpAndSettle();

    expect(find.text('Add record'), findsOneWidget);
    expect(find.byTooltip('Edit'), findsNothing);
    expect(find.byTooltip('Delete'), findsNothing);
  });

  testWidgets('table layout is used from 600dp, not master-detail', (tester) async {
    tester.view.physicalSize = const Size(640, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(pumpable(owner));
    await tester.pumpAndSettle();

    expect(find.text('Entered by'), findsOneWidget);
    expect(find.text('Add record'), findsOneWidget);
    expect(find.text('Expense name'), findsOneWidget);
    expect(find.text('Select a record to view it here.'), findsNothing);
  });

  testWidgets('Purchases table uses purchase columns, not Expenses', (tester) async {
    await setDesktop(tester);
    const purchases = PageSchema(
      page: Page(
        id: 'page-exp',
        companyId: 'company-1',
        key: 'purchases',
        name: 'Purchases for Cash',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
        dateColumnKey: 'purchase_date',
      ),
      columns: [
        PageColumn(
          id: 'p0',
          pageId: 'page-exp',
          key: 'purchase_date',
          name: 'Purchase Date',
          dataType: ColumnType.date,
          position: 0,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'p1',
          pageId: 'page-exp',
          key: 'entry_time',
          name: 'Entry Time',
          dataType: ColumnType.datetime,
          position: 1,
          isRequired: false,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'p2',
          pageId: 'page-exp',
          key: 'purchase_name',
          name: 'Purchase Name',
          dataType: ColumnType.text,
          position: 2,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'p3',
          pageId: 'page-exp',
          key: 'total_amount',
          name: 'Total Amount',
          dataType: ColumnType.currency,
          position: 3,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
      ],
    );
    const purchaseRecord = PageRecord(
      id: 'record-1',
      companyId: 'company-1',
      pageId: 'page-exp',
      occurredAt: '2026-09-13T10:00:00+05:30',
      businessDate: '2026-09-13',
      status: RecordStatus.active,
      data: {'purchase_name': 'Rice 50kg', 'total_amount': '85000.00'},
      needsReview: false,
      version: 1,
      createdBy: 'owner-1',
    );

    await tester.pumpWidget(pumpable(owner, pageSchema: purchases, pageRecord: purchaseRecord));
    await tester.pumpAndSettle();

    expect(find.text('Purchases for Cash'), findsWidgets);
    expect(find.text('Purchase Name'), findsOneWidget);
    expect(find.text('Total Amount'), findsOneWidget);
    expect(find.text('Rice 50kg'), findsOneWidget);
    expect(find.text('Rs. 85,000'), findsOneWidget);
    expect(find.text('Entered by'), findsOneWidget);
    expect(find.text('Description'), findsNothing);
    expect(find.text('Expense name'), findsNothing);
    expect(find.text('Entry Time'), findsNothing);
    expect(find.text('Purchase Date'), findsNothing);
  });

  testWidgets('Cheques table shows number, payee, amount and status', (tester) async {
    await setDesktop(tester);
    const cheques = PageSchema(
      page: Page(
        id: 'page-exp',
        companyId: 'company-1',
        key: 'cheques',
        name: 'Cheques',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
        dateColumnKey: 'cheque_date',
      ),
      columns: [
        PageColumn(
          id: 'c0',
          pageId: 'page-exp',
          key: 'cheque_number',
          name: 'Cheque Number',
          dataType: ColumnType.text,
          position: 0,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'c1',
          pageId: 'page-exp',
          key: 'payee_name',
          name: 'Payee Name',
          dataType: ColumnType.text,
          position: 1,
          isRequired: false,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'c2',
          pageId: 'page-exp',
          key: 'amount',
          name: 'Amount',
          dataType: ColumnType.currency,
          position: 2,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'c3',
          pageId: 'page-exp',
          key: 'cheque_date',
          name: 'Cheque Date',
          dataType: ColumnType.date,
          position: 3,
          isRequired: false,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'c4',
          pageId: 'page-exp',
          key: 'cheque_status',
          name: 'Status',
          dataType: ColumnType.select,
          position: 4,
          isRequired: false,
          isIndexed: false,
          isProtected: true,
          config: {
            'options': ['PENDING', 'PAID'],
          },
          isArchived: false,
        ),
      ],
    );
    const chequeRecord = PageRecord(
      id: 'record-1',
      companyId: 'company-1',
      pageId: 'page-exp',
      occurredAt: '2026-09-13T10:00:00+05:30',
      businessDate: '2026-09-13',
      status: RecordStatus.active,
      data: {
        'cheque_number': 'CHQ-1042',
        'payee_name': 'Ceylon Electricity',
        'amount': '52400.00',
        'cheque_status': 'PENDING',
      },
      needsReview: false,
      version: 1,
      createdBy: 'owner-1',
    );

    await tester.pumpWidget(pumpable(owner, pageSchema: cheques, pageRecord: chequeRecord));
    await tester.pumpAndSettle();

    expect(find.text('Cheque Number'), findsOneWidget);
    expect(find.text('Payee Name'), findsOneWidget);
    expect(find.text('Amount'), findsOneWidget);
    expect(find.text('Status'), findsOneWidget);
    expect(find.text('CHQ-1042'), findsOneWidget);
    expect(find.text('Ceylon Electricity'), findsOneWidget);
    expect(find.text('Pending'), findsOneWidget);
    expect(find.text('Cheque Date'), findsNothing);
    expect(find.text('Expense name'), findsNothing);
  });

  test('tableColumnsFor keeps each page\'s own fields', () {
    expect(
      tableColumnsFor(schema).map((c) => c.key).toList(),
      ['expense_name', 'description', 'amount'],
    );
  });

  testWidgets('Daily Revenue at 640dp shows cash/card/total, not a split pane', (tester) async {
    tester.view.physicalSize = const Size(640, 900);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    const revenue = PageSchema(
      page: Page(
        id: 'page-exp',
        companyId: 'company-1',
        key: 'daily_revenue',
        name: 'Daily Revenue',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
        dateColumnKey: 'entry_date',
      ),
      columns: [
        PageColumn(
          id: 'd0',
          pageId: 'page-exp',
          key: 'entry_date',
          name: 'Entry Date',
          dataType: ColumnType.date,
          position: 0,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'd1',
          pageId: 'page-exp',
          key: 'cash_sales',
          name: 'Cash Sales',
          dataType: ColumnType.currency,
          position: 1,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'd2',
          pageId: 'page-exp',
          key: 'card_sales',
          name: 'Card Sales',
          dataType: ColumnType.currency,
          position: 2,
          isRequired: true,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
        PageColumn(
          id: 'd3',
          pageId: 'page-exp',
          key: 'total_revenue',
          name: 'Total Revenue',
          dataType: ColumnType.currency,
          position: 3,
          isRequired: false,
          isIndexed: false,
          isProtected: false,
          config: {},
          isArchived: false,
        ),
      ],
    );
    const revenueRecord = PageRecord(
      id: 'record-1',
      companyId: 'company-1',
      pageId: 'page-exp',
      occurredAt: '2026-09-16T10:00:00+05:30',
      businessDate: '2026-09-16',
      status: RecordStatus.active,
      data: {
        'cash_sales': '180000.00',
        'card_sales': '70000.00',
        'total_revenue': '250000.00',
      },
      needsReview: false,
      version: 1,
      createdBy: 'owner-1',
    );

    await tester.pumpWidget(pumpable(owner, pageSchema: revenue, pageRecord: revenueRecord));
    await tester.pumpAndSettle();

    expect(find.text('Daily Revenue'), findsWidgets);
    expect(find.text('Cash Sales'), findsOneWidget);
    expect(find.text('Card Sales'), findsOneWidget);
    expect(find.text('Total Revenue'), findsOneWidget);
    expect(find.text('Rs. 180,000'), findsOneWidget);
    expect(find.text('Rs. 70,000'), findsOneWidget);
    expect(find.text('Rs. 250,000'), findsOneWidget);
    expect(find.text('16 Sep 2026'), findsOneWidget);
    expect(find.text('Select a record to view it here.'), findsNothing);
    expect(find.text('Entry Date'), findsNothing);
  });
}
