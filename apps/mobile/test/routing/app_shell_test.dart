import 'package:dio/dio.dart';
import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:velmart/core/storage/secure_store.dart';
import 'package:velmart/features/auth/application/auth_controller.dart';
import 'package:velmart/features/auth/data/auth_repository.dart';
import 'package:velmart/features/auth/domain/user.dart';
import 'package:velmart/features/pages/domain/page.dart';
import 'package:velmart/routing/app_shell.dart';

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

Widget _pumpable(UserRole role) {
  final router = GoRouter(
    initialLocation: '/home',
    routes: [
      ShellRoute(
        builder: (context, state, child) =>
            AppShell(location: state.matchedLocation, child: child),
        routes: [
          GoRoute(path: '/home', builder: (context, state) => const Text('home-body')),
          GoRoute(path: '/pages', builder: (context, state) => const Text('pages-body')),
          GoRoute(path: '/ai', builder: (context, state) => const Text('ai-body')),
          GoRoute(path: '/more', builder: (context, state) => const Text('more-body')),
          GoRoute(path: '/users', builder: (context, state) => const Text('users-body')),
          GoRoute(path: '/audit', builder: (context, state) => const Text('audit-body')),
        ],
      ),
    ],
  );

  return ProviderScope(
    overrides: [
      authRepositoryProvider.overrideWithValue(_FakeAuthRepository(_userWithRole(role))),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  Future<void> setSize(WidgetTester tester, Size size) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
  }

  testWidgets('Owner compact shell is Home, Pages, +, AI, More', (tester) async {
    await setSize(tester, const Size(390, 844));
    await tester.pumpWidget(_pumpable(UserRole.owner));
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsWidgets);
    expect(find.text('Pages'), findsOneWidget);
    expect(find.text('AI'), findsOneWidget);
    expect(find.text('More'), findsOneWidget);
    expect(find.byKey(const Key('nav-center-plus')), findsOneWidget);
    expect(find.text('home-body'), findsOneWidget);
  });

  testWidgets('Manager compact shell has no AI tab', (tester) async {
    await setSize(tester, const Size(390, 844));
    await tester.pumpWidget(_pumpable(UserRole.manager));
    await tester.pumpAndSettle();

    expect(find.text('Home'), findsWidgets);
    expect(find.text('Pages'), findsOneWidget);
    expect(find.text('More'), findsOneWidget);
    expect(find.text('AI'), findsNothing);
    expect(find.byKey(const Key('nav-center-plus')), findsOneWidget);
  });

  testWidgets('Manager compact bar is Home, Pages, Add, More', (tester) async {
    await setSize(tester, const Size(390, 844));
    await tester.pumpWidget(_pumpable(UserRole.manager));
    await tester.pumpAndSettle();

    expect(find.text('Add'), findsOneWidget);
    final home = tester.getCenter(find.text('Home').last);
    final pages = tester.getCenter(find.text('Pages'));
    final add = tester.getCenter(find.text('Add'));
    final more = tester.getCenter(find.text('More'));
    expect(home.dx, lessThan(pages.dx));
    expect(pages.dx, lessThan(add.dx));
    expect(add.dx, lessThan(more.dx));
  });

  testWidgets('Owner expanded shell docks Ask Velmart and shows OWNER extras', (tester) async {
    await setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(_pumpable(UserRole.owner));
    await tester.pumpAndSettle();

    expect(find.text('OWNER'), findsOneWidget);
    expect(find.text('Users'), findsOneWidget);
    expect(find.text('Audit'), findsOneWidget);
    expect(find.text('Settings'), findsOneWidget);
    expect(find.text('Ask Velmart'), findsOneWidget);
    expect(find.text('AI'), findsNothing);
    expect(find.byKey(const Key('nav-center-plus')), findsNothing);
  });

  testWidgets('Owner expanded /ai does not dock a second Ask Velmart pane', (tester) async {
    await setSize(tester, const Size(1280, 800));
    final router = GoRouter(
      initialLocation: '/ai',
      routes: [
        ShellRoute(
          builder: (context, state, child) =>
              AppShell(location: state.matchedLocation, child: child),
          routes: [
            GoRoute(path: '/home', builder: (context, state) => const Text('home-body')),
            GoRoute(path: '/pages', builder: (context, state) => const Text('pages-body')),
            GoRoute(path: '/ai', builder: (context, state) => const Text('ai-body')),
            GoRoute(path: '/more', builder: (context, state) => const Text('more-body')),
          ],
        ),
      ],
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          authRepositoryProvider.overrideWithValue(_FakeAuthRepository(_userWithRole(UserRole.owner))),
        ],
        child: MaterialApp.router(routerConfig: router),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('ai-body'), findsOneWidget);
    expect(find.text('Ask Velmart'), findsNothing);
  });

  testWidgets('Manager expanded shell has no AI pane and no OWNER group', (tester) async {
    await setSize(tester, const Size(1280, 800));
    await tester.pumpWidget(_pumpable(UserRole.manager));
    await tester.pumpAndSettle();

    expect(find.text('OWNER'), findsNothing);
    expect(find.text('Ask Velmart'), findsNothing);
    expect(find.text('More'), findsOneWidget);
  });

  testWidgets('page picker sheet scrolls a long list without overflowing', (tester) async {
    await setSize(tester, const Size(390, 700));

    const pages = [
      Page(
        id: '1',
        companyId: 'c',
        key: 'aa',
        name: 'aa',
        kind: PageKind.register,
        isArchived: false,
        isSystem: false,
        version: 1,
      ),
      Page(
        id: '2',
        companyId: 'c',
        key: 'cash_ledger',
        name: 'Cash Ledger',
        kind: PageKind.ledger,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
      Page(
        id: '3',
        companyId: 'c',
        key: 'cheques',
        name: 'Cheques',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
      Page(
        id: '4',
        companyId: 'c',
        key: 'daily_revenue',
        name: 'Daily Revenue',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
      Page(
        id: '5',
        companyId: 'c',
        key: 'debug',
        name: 'Debug Test Page',
        kind: PageKind.register,
        isArchived: false,
        isSystem: false,
        version: 1,
      ),
      Page(
        id: '6',
        companyId: 'c',
        key: 'employee_salary',
        name: 'Employee Salary',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
      Page(
        id: '7',
        companyId: 'c',
        key: 'expenses',
        name: 'Expenses',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
      Page(
        id: '8',
        companyId: 'c',
        key: 'purchases',
        name: 'Purchases for Cash',
        kind: PageKind.register,
        isArchived: false,
        isSystem: true,
        version: 1,
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showModalBottomSheet<Page>(
                context: context,
                isScrollControlled: true,
                showDragHandle: true,
                builder: (context) => const PagePickerSheet(pages: pages),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );

    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    expect(find.text('Add record to'), findsOneWidget);
    expect(find.text('aa'), findsOneWidget);
    await tester.scrollUntilVisible(find.text('Purchases for Cash'), 80);
    expect(find.text('Purchases for Cash'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
