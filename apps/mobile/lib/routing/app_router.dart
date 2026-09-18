import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/ai/presentation/ai_chat_screen.dart';
import '../features/auth/application/auth_controller.dart';
import '../features/auth/presentation/home_screen.dart';
import '../features/auth/presentation/login_screen.dart';
import '../features/auth/presentation/more_screen.dart';
import '../features/audit/presentation/audit_screen.dart';
import '../features/dashboard/presentation/reconciliation_screen.dart';
import '../features/pages/presentation/access_editor_screen.dart';
import '../features/pages/presentation/column_editor_screen.dart';
import '../features/pages/presentation/page_builder_screen.dart';
import '../features/pages/presentation/page_list_screen.dart';
import '../features/pages/presentation/record_detail_screen.dart';
import '../features/pages/presentation/record_form_screen.dart';
import '../features/pages/presentation/record_list_screen.dart';
import '../features/users/presentation/users_screen.dart';
import 'app_shell.dart';
import 'guards.dart';

final routerProvider = Provider<GoRouter>((ref) {
  final refreshNotifier = RouterRefreshNotifier(ref);

  return GoRouter(
    initialLocation: '/login',
    refreshListenable: refreshNotifier,
    redirect: (context, state) {
      final authState = ref.read(authControllerProvider);
      return authRedirect(authState, state.matchedLocation);
    },
    routes: [
      GoRoute(path: '/login', name: 'login', builder: (context, state) => const LoginScreen()),
      ShellRoute(
        builder: (context, state, child) =>
            AppShell(location: state.matchedLocation, child: child),
        routes: [
          GoRoute(path: '/home', name: 'home', builder: (context, state) => const HomeScreen()),
          GoRoute(path: '/pages', name: 'pages', builder: (context, state) => const PageListScreen()),
          GoRoute(
            path: '/pages/:pageId/records',
            name: 'pageRecords',
            builder: (context, state) =>
                RecordListScreen(pageId: state.pathParameters['pageId']!),
          ),
          GoRoute(path: '/ai', name: 'ai', builder: (context, state) => const AiChatScreen()),
          GoRoute(path: '/more', name: 'more', builder: (context, state) => const MoreScreen()),
          GoRoute(
            path: '/reconciliation',
            name: 'reconciliation',
            builder: (context, state) => const ReconciliationScreen(),
          ),
          GoRoute(path: '/audit', name: 'audit', builder: (context, state) => const AuditScreen()),
          GoRoute(path: '/users', name: 'users', builder: (context, state) => const UsersScreen()),
        ],
      ),
      GoRoute(
        path: '/pages/new',
        name: 'pageNew',
        builder: (context, state) => const PageBuilderScreen(),
      ),
      GoRoute(
        path: '/pages/:pageId/columns',
        name: 'pageColumns',
        builder: (context, state) =>
            ColumnEditorScreen(pageId: state.pathParameters['pageId']!),
      ),
      GoRoute(
        path: '/pages/:pageId/access',
        name: 'pageAccess',
        builder: (context, state) =>
            AccessEditorScreen(pageId: state.pathParameters['pageId']!),
      ),
      GoRoute(
        path: '/pages/:pageId/records/new',
        name: 'recordNew',
        builder: (context, state) =>
            RecordFormScreen(pageId: state.pathParameters['pageId']!),
      ),
      GoRoute(
        path: '/records/:recordId',
        name: 'recordDetail',
        builder: (context, state) =>
            RecordDetailScreen(recordId: state.pathParameters['recordId']!),
      ),
      GoRoute(
        path: '/records/:recordId/edit',
        name: 'recordEdit',
        builder: (context, state) =>
            RecordFormScreen(recordId: state.pathParameters['recordId']!),
      ),
    ],
  );
});
