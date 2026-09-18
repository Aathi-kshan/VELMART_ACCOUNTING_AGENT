import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:velmart/core/money/money.dart';
import 'package:velmart/core/storage/secure_store.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/application/home_providers.dart';
import 'package:velmart/features/auth/data/auth_repository.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/auth/presentation/home_screen.dart';
import 'package:velmart/features/dashboard/domain/reconciliation.dart';
import 'package:velmart/features/pages/domain/record.dart';

class _FakeAuthRepository extends AuthRepository {
  _FakeAuthRepository() : super(dio: Dio(), secureStore: SecureStore());

  @override
  Future<User> fetchMe() async => const User(
    id: 'owner-1',
    companyId: 'company-1',
    fullName: 'Aathi',
    email: 'aathi@velmart.lk',
    role: UserRole.owner,
    storeIds: [],
  );
}

HomeDashboard get _dashboard => HomeDashboard(
  todayLabel: 'Sunday 13 September · as of 21:14',
  todayRevenue: Money.parse('250000.00'),
  previousRevenue: Money.parse('238322.00'),
  cashSales: Money.parse('180000.00'),
  cardSales: Money.parse('70000.00'),
  todayRecordCount: 1,
  mismatch: ReconciliationItem(
    businessDate: '2026-09-13',
    revenueTotal: Money.parse('250000.00'),
    ledgerTotal: Money.parse('248000.00'),
    difference: Money.parse('2000.00'),
  ),
  monthExpenses: Money.parse('1284400.00'),
  lastMonthExpenses: Money.parse('1146785.00'),
  monthPurchases: Money.parse('4062000.00'),
  lastMonthPurchases: Money.parse('4187628.00'),
  expenseBreakdown: const [
    AggregateGroup(key: 'Electricity', value: '587400.00', count: 1),
    AggregateGroup(key: 'Rent', value: '525000.00', count: 1),
    AggregateGroup(key: 'Carriage', value: '318000.00', count: 1),
    AggregateGroup(key: 'Repairs', value: '142000.00', count: 1),
  ],
  pendingCheques: const [
    PageRecord(
      id: 'c1',
      companyId: 'company-1',
      pageId: 'cheques',
      occurredAt: '2026-09-13T10:00:00+05:30',
      businessDate: '2026-09-13',
      status: RecordStatus.active,
      data: {
        'payee_name': 'Sunrise Distributors',
        'cheque_number': '445120',
        'cheque_date': '2026-09-18',
        'amount': '186000.00',
      },
      needsReview: false,
      version: 1,
      createdBy: 'owner-1',
    ),
  ],
  pendingCount: 3,
  chequesTotalCount: 4,
);

void main() {
  testWidgets('home matches the prototype chrome and copy', (tester) async {
    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (context, state) => const HomeScreen()),
        GoRoute(path: '/reconciliation', name: 'reconciliation', builder: (_, __) => const SizedBox()),
        GoRoute(
          path: '/pages/:pageId/records',
          name: 'pageRecords',
          builder: (_, __) => const SizedBox(),
        ),
        GoRoute(
          path: '/records/:recordId',
          name: 'recordDetail',
          builder: (_, __) => const SizedBox(),
        ),
      ],
    );

    tester.view.physicalSize = const Size(390, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(_FakeAuthRepository()),
          homeDashboardProvider.overrideWith((ref) async => _dashboard),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsOneWidget);
    expect(find.text('Sunday 13 September · as of 21:14'), findsOneWidget);
    expect(find.text('A'), findsOneWidget);
    expect(find.text('Total revenue'), findsOneWidget);
    expect(find.text('Rs. 250,000'), findsOneWidget);
    expect(find.textContaining('Today · 1 record'), findsOneWidget);
    expect(find.text('Cash sales'), findsOneWidget);
    expect(find.text('Rs. 180,000'), findsOneWidget);
    expect(find.text('Card sales'), findsOneWidget);
    expect(find.text('Rs. 70,000'), findsOneWidget);
    expect(find.text('Difference of Rs. 2,000 on 13 September'), findsOneWidget);
    expect(find.text('THIS MONTH'), findsOneWidget);
    expect(find.text('Total expenses'), findsOneWidget);
    expect(find.text('Rs. 1,284,400'), findsOneWidget);
    expect(find.text('Purchases for Cash'), findsOneWidget);
    expect(find.text('Rs. 4,062,000'), findsOneWidget);
    expect(find.text('Expenses by name'), findsOneWidget);
    expect(find.text('Pending cheques'), findsOneWidget);
    expect(find.text('3 of 4'), findsOneWidget);
    expect(find.text('Sunrise Distributors'), findsOneWidget);
    expect(find.text('#445120 · due 18 Sep 2026'), findsOneWidget);
  });
}
