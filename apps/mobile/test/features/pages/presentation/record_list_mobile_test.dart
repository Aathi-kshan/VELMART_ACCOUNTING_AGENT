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

PageColumn _col({
  required String key,
  required String name,
  required ColumnType type,
  required int position,
  bool required = false,
  bool protected = false,
  Map<String, dynamic> config = const {},
}) {
  return PageColumn(
    id: key,
    pageId: 'page-1',
    key: key,
    name: name,
    dataType: type,
    position: position,
    isRequired: required,
    isIndexed: false,
    isProtected: protected,
    config: config,
    isArchived: false,
  );
}

Page _page({
  required String key,
  required String name,
  String? dateColumnKey,
}) {
  return Page(
    id: 'page-1',
    companyId: 'company-1',
    key: key,
    name: name,
    kind: PageKind.register,
    isArchived: false,
    isSystem: true,
    version: 1,
    dateColumnKey: dateColumnKey,
  );
}

PageRecord _record(Map<String, dynamic> data, {String date = '2026-09-16'}) {
  return PageRecord(
    id: 'record-1',
    companyId: 'company-1',
    pageId: 'page-1',
    occurredAt: '${date}T10:00:00+05:30',
    businessDate: date,
    status: RecordStatus.active,
    data: data,
    needsReview: false,
    version: 1,
    createdBy: 'owner-1',
  );
}

void main() {
  setUpAll(() {
    registerFallbackValue(const RecordQuery());
    registerFallbackValue(const AggregateQuery(metric: AggregateMetric.count));
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

  final expenses = PageSchema(
    page: _page(key: 'expenses', name: 'Expenses', dateColumnKey: 'expense_date'),
    columns: [
      _col(key: 'expense_date', name: 'Expense Date', type: ColumnType.date, position: 0, required: true),
      _col(key: 'entry_time', name: 'Entry Time', type: ColumnType.datetime, position: 1),
      _col(key: 'expense_name', name: 'Expense Name', type: ColumnType.text, position: 2, required: true),
      _col(key: 'amount', name: 'Amount', type: ColumnType.currency, position: 3, required: true),
      _col(key: 'description', name: 'Description', type: ColumnType.longText, position: 4),
    ],
  );

  final purchases = PageSchema(
    page: _page(key: 'purchases', name: 'Purchases for Cash', dateColumnKey: 'purchase_date'),
    columns: [
      _col(key: 'purchase_date', name: 'Purchase Date', type: ColumnType.date, position: 0, required: true),
      _col(key: 'entry_time', name: 'Entry Time', type: ColumnType.datetime, position: 1),
      _col(key: 'purchase_name', name: 'Purchase Name', type: ColumnType.text, position: 2, required: true),
      _col(key: 'total_amount', name: 'Total Amount', type: ColumnType.currency, position: 3, required: true),
    ],
  );

  final cheques = PageSchema(
    page: _page(key: 'cheques', name: 'Cheques', dateColumnKey: 'cheque_date'),
    columns: [
      _col(key: 'cheque_number', name: 'Cheque Number', type: ColumnType.text, position: 0, required: true),
      _col(key: 'payee_name', name: 'Payee Name', type: ColumnType.text, position: 1),
      _col(key: 'amount', name: 'Amount', type: ColumnType.currency, position: 2, required: true),
      _col(key: 'cheque_date', name: 'Cheque Date', type: ColumnType.date, position: 3),
      _col(
        key: 'cheque_status',
        name: 'Status',
        type: ColumnType.select,
        position: 4,
        protected: true,
        config: const {'options': ['PENDING', 'PAID']},
      ),
      _col(key: 'reference', name: 'Reference', type: ColumnType.text, position: 5),
    ],
  );

  final revenue = PageSchema(
    page: _page(key: 'daily_revenue', name: 'Daily Revenue', dateColumnKey: 'entry_date'),
    columns: [
      _col(key: 'entry_date', name: 'Entry Date', type: ColumnType.date, position: 0, required: true),
      _col(key: 'cash_sales', name: 'Cash Sales', type: ColumnType.currency, position: 1, required: true),
      _col(key: 'card_sales', name: 'Card Sales', type: ColumnType.currency, position: 2, required: true),
      _col(key: 'total_revenue', name: 'Total Revenue', type: ColumnType.currency, position: 3),
    ],
    generatedColumns: const {'total_revenue'},
  );

  final ledger = PageSchema(
    page: _page(key: 'cash_ledger', name: 'Cash Ledger', dateColumnKey: 'entry_date'),
    columns: [
      _col(key: 'entry_date', name: 'Entry Date', type: ColumnType.date, position: 0, required: true),
      _col(key: 'cash_amount', name: 'Cash Amount', type: ColumnType.currency, position: 1, required: true),
      _col(key: 'card_sales_amount', name: 'Card Sales Amount', type: ColumnType.currency, position: 2, required: true),
      _col(key: 'total_amount', name: 'Total Amount', type: ColumnType.currency, position: 3),
    ],
    generatedColumns: const {'total_amount'},
  );

  final salary = PageSchema(
    page: _page(key: 'employee_salary', name: 'Employee Salary', dateColumnKey: 'payment_date'),
    columns: [
      _col(key: 'payment_date', name: 'Payment Date', type: ColumnType.date, position: 0, required: true),
      _col(key: 'employee_name', name: 'Employee Name', type: ColumnType.text, position: 1, required: true),
      _col(key: 'paid_amount', name: 'Paid Amount', type: ColumnType.currency, position: 2, required: true),
      _col(key: 'reference', name: 'Reference', type: ColumnType.text, position: 3),
    ],
  );

  late MockPageRepository mockRepository;
  late MockAuthRepository mockAuthRepository;

  setUp(() {
    mockRepository = MockPageRepository();
    mockAuthRepository = MockAuthRepository();
    when(() => mockRepository.aggregate(any(), any())).thenAnswer(
      (_) async => const AggregateResult(value: '0', recordCount: 1, groups: []),
    );
    when(() => mockRepository.listUsers()).thenAnswer((_) async => [owner, manager]);
  });

  Future<void> setPhone(WidgetTester tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  Widget pumpable({
    required User user,
    required PageSchema schema,
    required PageRecord record,
  }) {
    when(() => mockAuthRepository.fetchMe()).thenAnswer((_) async => user);
    when(() => mockRepository.getSchema(any())).thenAnswer((_) async => schema);
    when(
      () => mockRepository.queryRecords(any(), any()),
    ).thenAnswer((_) async => Paginated(items: [record]));
    final router = GoRouter(
      initialLocation: '/pages/page-1/records',
      routes: [
        GoRoute(
          path: '/pages/:pageId/records',
          builder: (context, state) =>
              RecordListScreen(pageId: state.pathParameters['pageId']!),
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

  group('recordCardDetails (compact fields per page)', () {
    test('Expenses: name, date, amount, description', () {
      final details = recordCardDetails(
        expenses,
        _record({
          'expense_name': 'Electricity',
          'amount': '52400.00',
          'description': 'CEB bill',
        }, date: '2026-09-13'),
      );
      expect(details.title, 'Electricity');
      expect(details.subtitle, '13 Sep 2026');
      expect(details.amount, '52400.00');
      expect(details.supporting, ['Description: CEB bill']);
    });

    test('Purchases: name and total, no description', () {
      final details = recordCardDetails(
        purchases,
        _record({'purchase_name': 'Rice 50kg', 'total_amount': '85000.00'}),
      );
      expect(details.title, 'Rice 50kg');
      expect(details.subtitle, '16 Sep 2026');
      expect(details.amount, '85000.00');
      expect(details.supporting, isEmpty);
    });

    test('Cheques: number, amount, payee and status', () {
      final details = recordCardDetails(
        cheques,
        _record({
          'cheque_number': 'CHQ-1042',
          'payee_name': 'Ceylon Electricity',
          'amount': '52400.00',
          'cheque_status': 'PENDING',
          'reference': 'Aug bill',
        }),
      );
      expect(details.title, 'CHQ-1042');
      expect(details.subtitle, '16 Sep 2026');
      expect(details.amount, '52400.00');
      expect(details.supporting, [
        'Payee Name: Ceylon Electricity',
        'Status: Pending',
      ]);
    });

    test('Daily Revenue: date title, total as amount, cash and card as extras', () {
      final details = recordCardDetails(
        revenue,
        _record({
          'cash_sales': '180000.00',
          'card_sales': '70000.00',
          'total_revenue': '250000.00',
        }),
      );
      expect(details.title, '16 Sep 2026');
      expect(details.subtitle, isNull);
      expect(details.amount, '250000.00');
      expect(details.supporting, [
        'Cash Sales: Rs. 180,000',
        'Card Sales: Rs. 70,000',
      ]);
    });

    test('Cash Ledger: date title, total as amount', () {
      final details = recordCardDetails(
        ledger,
        _record({
          'cash_amount': '180000.00',
          'card_sales_amount': '70000.00',
          'total_amount': '250000.00',
        }),
      );
      expect(details.title, '16 Sep 2026');
      expect(details.amount, '250000.00');
      expect(details.supporting, [
        'Cash Amount: Rs. 180,000',
        'Card Sales Amount: Rs. 70,000',
      ]);
    });

    test('Employee Salary: name, paid amount, reference', () {
      final details = recordCardDetails(
        salary,
        _record({
          'employee_name': 'Nimal Perera',
          'paid_amount': '45000.00',
          'reference': 'September',
        }),
      );
      expect(details.title, 'Nimal Perera');
      expect(details.subtitle, '16 Sep 2026');
      expect(details.amount, '45000.00');
      expect(details.supporting, ['Reference: September']);
    });
  });

  group('compact list (<600dp) renders those details', () {
    testWidgets('Expenses card', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: expenses,
          record: _record({
            'expense_name': 'Electricity',
            'amount': '52400.00',
            'description': 'CEB bill',
          }, date: '2026-09-13'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Expenses'), findsWidgets);
      expect(find.text('Electricity'), findsOneWidget);
      expect(find.text('13 Sep 2026'), findsOneWidget);
      expect(find.text('Rs. 52,400'), findsOneWidget);
      expect(find.textContaining('CEB bill'), findsOneWidget);
      expect(find.text('Entered by'), findsNothing);
      expect(find.text('Purchase Name'), findsNothing);
    });

    testWidgets('Purchases card', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: purchases,
          record: _record({'purchase_name': 'Rice 50kg', 'total_amount': '85000.00'}),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Purchases for Cash'), findsWidgets);
      expect(find.text('Rice 50kg'), findsOneWidget);
      expect(find.text('Rs. 85,000'), findsOneWidget);
      expect(find.text('Description'), findsNothing);
      expect(find.text('Expense Name'), findsNothing);
    });

    testWidgets('Cheques card', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: cheques,
          record: _record({
            'cheque_number': 'CHQ-1042',
            'payee_name': 'Ceylon Electricity',
            'amount': '52400.00',
            'cheque_status': 'PENDING',
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Cheques'), findsWidgets);
      expect(find.text('CHQ-1042'), findsOneWidget);
      expect(find.text('Rs. 52,400'), findsOneWidget);
      expect(find.textContaining('Ceylon Electricity'), findsOneWidget);
      expect(find.textContaining('Pending'), findsWidgets);
    });

    testWidgets('Daily Revenue card uses total, not only cash', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: revenue,
          record: _record({
            'cash_sales': '180000.00',
            'card_sales': '70000.00',
            'total_revenue': '250000.00',
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Daily Revenue'), findsWidgets);
      expect(find.text('16 Sep 2026'), findsOneWidget);
      expect(find.text('Rs. 250,000'), findsOneWidget);
      expect(find.textContaining('Rs. 180,000'), findsOneWidget);
      expect(find.textContaining('Rs. 70,000'), findsOneWidget);
      expect(find.text('Select a record to view it here.'), findsNothing);
    });

    testWidgets('Cash Ledger card', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: ledger,
          record: _record({
            'cash_amount': '180000.00',
            'card_sales_amount': '70000.00',
            'total_amount': '250000.00',
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Cash Ledger'), findsWidgets);
      expect(find.text('16 Sep 2026'), findsOneWidget);
      expect(find.text('Rs. 250,000'), findsOneWidget);
    });

    testWidgets('Employee Salary card', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: owner,
          schema: salary,
          record: _record({
            'employee_name': 'Nimal Perera',
            'paid_amount': '45000.00',
            'reference': 'September',
          }),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Employee Salary'), findsWidgets);
      expect(find.text('Nimal Perera'), findsOneWidget);
      expect(find.text('Rs. 45,000'), findsOneWidget);
      expect(find.text('Reference: September'), findsOneWidget);
    });

    testWidgets('Manager compact card has no edit or delete', (tester) async {
      await setPhone(tester);
      await tester.pumpWidget(
        pumpable(
          user: manager,
          schema: expenses,
          record: _record({
            'expense_name': 'Electricity',
            'amount': '52400.00',
            'description': 'CEB bill',
          }, date: '2026-09-13'),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byTooltip('Record actions'), findsNothing);
      expect(find.byTooltip('Edit'), findsNothing);
      expect(find.byTooltip('Delete'), findsNothing);
    });
  });
}
