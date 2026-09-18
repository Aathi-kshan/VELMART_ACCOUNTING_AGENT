import 'dart:async';

import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../core/navigation/active_page.dart';
import '../core/permissions/can.dart';
import '../core/theme/app_colors.dart';
import '../core/theme/app_spacing.dart';
import '../core/widgets/adaptive_scaffold.dart';
import '../features/ai/presentation/ai_chat_screen.dart';
import '../features/auth/application/auth_controller.dart';
import '../features/auth/domain/user.dart';
import '../features/pages/application/pages_providers.dart';
import '../features/pages/domain/page.dart';
import 'guards.dart';

/// Kept mounted across tab switches (`ShellRoute`), so this is also where
/// same-device "no manual refresh" sync lives (design brief §6/§10): an app
/// resume, or a page grant/rename/removal from another session, becomes
/// visible without the Owner/Manager doing anything. There is no server
/// push here — see [_AppShellState]'s doc comment for exactly what this
/// does and doesn't cover.
class AppShell extends ConsumerStatefulWidget {
  const AppShell({super.key, required this.child, required this.location});

  final Widget child;
  final String location;

  @override
  ConsumerState<AppShell> createState() => _AppShellState();
}

/// **What this delivers, honestly (no server push exists in this app):**
/// on app resume, [_lifecycleListener] invalidates `pagesProvider` so a
/// grant/revoke/rename/create/archive made from another session while this
/// one was backgrounded shows up the moment it's foregrounded. While the
/// Pages tab is actually on screen, [_pagesPoll] does the same thing every
/// 30s, so a change made by someone else lands without the user needing to
/// pull-to-refresh. Neither of these makes a record list live-update while
/// someone is sitting on it, and nothing here is instant — both are
/// deliberately narrow (Pages only, not app-wide) rather than a general
/// polling layer.
class _AppShellState extends ConsumerState<AppShell> {
  AppLifecycleListener? _lifecycleListener;
  Timer? _pagesPoll;

  static const _home = AdaptiveDestination(
    icon: Icons.home_outlined,
    selectedIcon: Icons.home,
    label: 'Home',
    path: '/home',
  );
  static const _pages = AdaptiveDestination(
    icon: Icons.table_chart_outlined,
    selectedIcon: Icons.table_chart,
    label: 'Pages',
    path: '/pages',
  );
  static const _ai = AdaptiveDestination(
    icon: Icons.auto_awesome,
    selectedIcon: Icons.auto_awesome,
    label: 'AI',
    path: '/ai',
  );
  static const _more = AdaptiveDestination(
    icon: Icons.menu,
    selectedIcon: Icons.menu,
    label: 'More',
    path: '/more',
  );

  static const _ownerExtras = [
    AdaptiveDestination(
      icon: Icons.person_add_outlined,
      selectedIcon: Icons.person_add,
      label: 'Users',
      path: '/users',
    ),
    AdaptiveDestination(
      icon: Icons.history,
      selectedIcon: Icons.history,
      label: 'Audit',
      path: '/audit',
    ),
    AdaptiveDestination(
      icon: Icons.tune,
      selectedIcon: Icons.tune,
      label: 'Settings',
      path: '/more',
    ),
  ];

  @override
  void initState() {
    super.initState();
    _lifecycleListener = AppLifecycleListener(
      onResume: () => ref.invalidate(pagesProvider),
    );
  }

  @override
  void dispose() {
    _lifecycleListener?.dispose();
    _pagesPoll?.cancel();
    super.dispose();
  }

  void _syncPagesPoll() {
    final onPagesTab = widget.location.startsWith('/pages');
    if (onPagesTab && _pagesPoll == null) {
      _pagesPoll = Timer.periodic(const Duration(seconds: 30), (_) {
        ref.invalidate(pagesProvider);
      });
    } else if (!onPagesTab && _pagesPoll != null) {
      _pagesPoll!.cancel();
      _pagesPoll = null;
    }
  }

  List<AdaptiveDestination> _tabsFor(UserRole role, {required bool expanded}) {
    if (expanded) {
      return canUseAi(role) ? const [_home, _pages] : const [_home, _pages, _more];
    }
    return canUseAi(role) ? const [_home, _pages, _ai, _more] : const [_home, _pages, _more];
  }

  int _selectedIndex(List<AdaptiveDestination> tabs, {required bool expanded}) {
    final location = widget.location;
    if (expanded &&
        (location.startsWith('/users') ||
            location.startsWith('/audit') ||
            location.startsWith('/more') ||
            location.startsWith('/reconciliation'))) {
      return -1;
    }
    if (location.startsWith('/pages')) {
      final i = tabs.indexWhere((d) => d.path == '/pages');
      return i >= 0 ? i : 0;
    }
    if (location.startsWith('/ai')) {
      final i = tabs.indexWhere((d) => d.path == '/ai');
      return i >= 0 ? i : -1;
    }
    if (location.startsWith('/more') ||
        location.startsWith('/audit') ||
        location.startsWith('/users') ||
        location.startsWith('/reconciliation')) {
      final i = tabs.indexWhere((d) => d.path == '/more');
      return i >= 0 ? i : 0;
    }
    return 0;
  }

  int? _selectedOwnerIndex() {
    final location = widget.location;
    if (location.startsWith('/users')) return 0;
    if (location.startsWith('/audit')) return 1;
    if (location.startsWith('/more') || location.startsWith('/reconciliation')) return 2;
    return null;
  }

  @override
  Widget build(BuildContext context) {
    _syncPagesPoll();
    final location = widget.location;
    final authState = ref.watch(authControllerProvider);
    final user = authState is AuthAuthenticated ? authState.user : null;
    final role = user?.role ?? UserRole.manager;
    final width = MediaQuery.sizeOf(context).width;
    final expanded = AdaptiveScaffold.isExpanded(width);
    final tabs = _tabsFor(role, expanded: expanded);
    final index = _selectedIndex(tabs, expanded: expanded);
    final active = ref.watch(activePageProvider);

    return AdaptiveScaffold(
      destinations: tabs,
      selectedIndex: index,
      onDestinationSelected: (next) {
        if (next < 0 || next >= tabs.length) return;
        final path = tabs[next].path;
        if (path != null) context.go(path);
      },
      ownerDestinations: canManageUsers(role) && expanded ? _ownerExtras : const [],
      selectedOwnerIndex: canManageUsers(role) && expanded ? _selectedOwnerIndex() : null,
      onOwnerDestinationSelected: (i) {
        final path = _ownerExtras[i].path;
        if (path != null) context.go(path);
      },
      centerAction: () => _onCenterPlus(context, ref, active, location),
      centerActionTooltip: active.hasPage && isRecordListLocation(location)
          ? 'Add record'
          : 'Add record to a page',
      trailingPane: canUseAi(role) && expanded && !location.startsWith('/ai')
          ? const AiChatScreen()
          : null,
      footer: user == null ? null : _AccountChip(user: user),
      body: widget.child,
    );
  }

  Future<void> _onCenterPlus(
    BuildContext context,
    WidgetRef ref,
    ActivePage active,
    String location,
  ) async {
    if (active.hasPage && isRecordListLocation(location)) {
      context.pushNamed('recordNew', pathParameters: {'pageId': active.id!});
      return;
    }
    final pages = await ref.read(pagesProvider.future);
    if (!context.mounted) return;
    if (pages.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No pages available to add a record to.')),
      );
      return;
    }
    if (pages.length == 1) {
      context.pushNamed('recordNew', pathParameters: {'pageId': pages.first.id});
      return;
    }
    final chosen = await showModalBottomSheet<Page>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => PagePickerSheet(pages: pages),
    );
    if (chosen == null || !context.mounted) return;
    context.pushNamed('recordNew', pathParameters: {'pageId': chosen.id});
  }
}

/// Page picker for the shell's center **+**. The list scrolls inside a
/// bounded height so a long catalog cannot overflow the sheet.
class PagePickerSheet extends StatelessWidget {
  const PagePickerSheet({super.key, required this.pages});

  final List<Page> pages;

  @override
  Widget build(BuildContext context) {
    final maxHeight = MediaQuery.sizeOf(context).height * 0.7;

    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(AppSpacing.md, 0, AppSpacing.md, AppSpacing.md),
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: maxHeight),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('Add record to', style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: AppSpacing.sm),
              Flexible(
                child: ListView.builder(
                  shrinkWrap: true,
                  itemCount: pages.length,
                  itemBuilder: (context, index) {
                    final page = pages[index];
                    return ListTile(
                      title: Text(page.name),
                      subtitle: page.description == null ? null : Text(page.description!),
                      onTap: () => Navigator.of(context).pop(page),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _AccountChip extends StatelessWidget {
  const _AccountChip({required this.user});

  final User user;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      child: Row(
        children: [
          CircleAvatar(
            radius: 14,
            backgroundColor: AppColors.brandPrimaryDark,
            child: Text(
              user.fullName.isEmpty ? '?' : user.fullName[0].toUpperCase(),
              style: const TextStyle(color: AppColors.textOnBrand, fontWeight: FontWeight.w600, fontSize: 12),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              user.fullName,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        ],
      ),
    );
  }
}
