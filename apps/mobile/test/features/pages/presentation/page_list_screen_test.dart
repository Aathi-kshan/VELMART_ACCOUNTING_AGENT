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
import 'package:velmart/features/pages/domain/page.dart';
import 'package:velmart/features/pages/presentation/page_list_screen.dart';

class MockPageRepository extends Mock implements PageRepository {}

class MockAuthRepository extends Mock implements AuthRepository {}

// A system page's schema changes only by migration (docs/API.md §1.7) —
// this proves the popup menu never offers Rename/Remove for one, only for
// an Owner-built custom page, and that confirming Remove calls the
// repository's archive method exactly once.
void main() {
  const owner = User(
    id: 'owner-1',
    companyId: 'company-1',
    fullName: 'Demo Owner',
    email: 'owner@test.lk',
    role: UserRole.owner,
    storeIds: [],
  );

  const systemPage = Page(
    id: 'page-system',
    companyId: 'company-1',
    key: 'purchases',
    name: 'Purchases for Cash',
    kind: PageKind.register,
    isArchived: false,
    isSystem: true,
    version: 1,
  );

  const customPage = Page(
    id: 'page-custom',
    companyId: 'company-1',
    key: 'supplier_contacts',
    name: 'Supplier Contacts',
    kind: PageKind.register,
    isArchived: false,
    isSystem: false,
    version: 1,
  );

  late MockPageRepository mockRepository;
  late MockAuthRepository mockAuthRepository;

  setUp(() {
    mockRepository = MockPageRepository();
    mockAuthRepository = MockAuthRepository();
    when(() => mockAuthRepository.fetchMe()).thenAnswer((_) async => owner);
    when(
      () => mockRepository.listPages(),
    ).thenAnswer((_) async => const [systemPage, customPage]);
  });

  Widget pumpable() {
    final router = GoRouter(
      initialLocation: '/',
      routes: [
        GoRoute(path: '/', builder: (context, state) => const Scaffold(body: PageListScreen())),
        GoRoute(
          path: '/pages/:pageId/columns',
          name: 'pageColumns',
          builder: (context, state) => const Scaffold(body: Text('columns')),
        ),
        GoRoute(
          path: '/pages/:pageId/access',
          name: 'pageAccess',
          builder: (context, state) => const Scaffold(body: Text('access')),
        ),
        GoRoute(
          path: '/pages/:pageId/records',
          name: 'pageRecords',
          builder: (context, state) => const Scaffold(body: Text('records')),
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

  testWidgets('a system page offers neither Rename nor Remove', (tester) async {
    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Page actions').first);
    await tester.pumpAndSettle();

    expect(find.text('Rename'), findsNothing);
    expect(find.text('Remove page'), findsNothing);
    expect(find.text('Manage access'), findsOneWidget);
  });

  testWidgets('a custom page offers Rename and Remove', (tester) async {
    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Page actions').last);
    await tester.pumpAndSettle();

    expect(find.text('Rename'), findsOneWidget);
    expect(find.text('Remove page'), findsOneWidget);
  });

  testWidgets('confirming Remove calls archivePage exactly once', (tester) async {
    when(() => mockRepository.archivePage('page-custom')).thenAnswer((_) async => customPage);

    await tester.pumpWidget(pumpable());
    await tester.pumpAndSettle();

    await tester.tap(find.byTooltip('Page actions').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Remove page'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilledButton, 'Remove'));
    await tester.pumpAndSettle();

    verify(() => mockRepository.archivePage('page-custom')).called(1);
  });
}
