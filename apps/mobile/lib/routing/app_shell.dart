import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/permissions/can.dart';
import '../core/widgets/adaptive_scaffold.dart';
import '../features/auth/application/auth_controller.dart';
import '../features/auth/domain/user.dart';

/// The persistent chrome every top-level tab renders inside (plan section
/// 22.4) — go_router's `ShellRoute` keeps this mounted across tab switches,
/// so the nav bar/rail/sidebar doesn't rebuild on every navigation.
///
/// Tabs are `Home · Pages · More` for both roles in P3 — the Owner's `AI`
/// tab arrives with P7 (that route doesn't exist yet, so it's absent rather
/// than a dead entry, per plan section 22.4: "a greyed-out feature invites
/// requests for access; an absent one does not.").
///
/// Screens nested here return content only, no `Scaffold`/`AppBar` of their
/// own — this shell owns the single AppBar (title changes per tab) and the
/// one contextual FAB, matching the "one app, three layouts" model rather
/// than nesting a Scaffold inside a Scaffold on every tab. Screens reached by
/// pushing on top of a tab (record forms, the page builder, ...) are plain
/// `GoRoute`s outside this shell and provide their own `Scaffold` normally.
class AppShell extends ConsumerWidget {
  const AppShell({super.key, required this.child, required this.location});

  final Widget child;
  final String location;

  static const _destinations = [
    AdaptiveDestination(icon: Icons.home_outlined, selectedIcon: Icons.home, label: 'Home'),
    AdaptiveDestination(
      icon: Icons.table_chart_outlined,
      selectedIcon: Icons.table_chart,
      label: 'Pages',
    ),
    AdaptiveDestination(icon: Icons.more_horiz, selectedIcon: Icons.more_horiz, label: 'More'),
  ];

  static const _paths = ['/home', '/pages', '/more'];
  static const _titles = ['Velmart', 'Pages', 'More'];

  int get _selectedIndex {
    if (location.startsWith('/pages')) return 1;
    if (location.startsWith('/more')) return 2;
    return 0;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;
    final index = _selectedIndex;

    return AdaptiveScaffold(
      title: _titles[index],
      actions: [
        IconButton(
          icon: const Icon(Icons.logout),
          tooltip: 'Sign out',
          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
        ),
      ],
      destinations: _destinations,
      selectedIndex: index,
      onDestinationSelected: (next) => context.go(_paths[next]),
      // Only the Pages tab gets a FAB, and only for an Owner — a manager
      // never creates a page (plan section 4.2); they add records from
      // inside a page's own record list instead.
      floatingActionButton: (index == 1 && canCreatePage(role))
          ? FloatingActionButton(
              onPressed: () => context.pushNamed('pageNew'),
              tooltip: 'New page',
              child: const Icon(Icons.add),
            )
          : null,
      body: child,
    );
  }
}
