import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radii.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/refreshable.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';

class PageListScreen extends ConsumerStatefulWidget {
  const PageListScreen({super.key});

  @override
  ConsumerState<PageListScreen> createState() => _PageListScreenState();
}

class _PageListScreenState extends ConsumerState<PageListScreen> {
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;
    final pages = ref.watch(pagesProvider);
    final query = _search.text.trim().toLowerCase();

    return pages.when(
      loading: () => PullToRefresh(
        onRefresh: () => ref.refresh(pagesProvider.future),
        child: const AppLoadingState(),
      ),
      error: (error, _) => PullToRefresh(
        onRefresh: () => ref.refresh(pagesProvider.future),
        child: AppErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(pagesProvider),
        ),
      ),
      data: (list) {
          final filtered = query.isEmpty
              ? list
              : list.where((p) => p.name.toLowerCase().contains(query) || p.key.contains(query)).toList();
          final shipped = filtered.where((p) => p.isSystem).toList();
          final built = filtered.where((p) => !p.isSystem).toList();

          if (list.isEmpty) {
            return PullToRefresh(
              onRefresh: () => ref.refresh(pagesProvider.future),
              child: EmptyState(
                icon: Icons.table_chart_outlined,
                title: canCreatePage(role) ? 'Build your first table' : 'No pages yet',
                message: canCreatePage(role)
                    ? 'Tap New page to create a table. The six core pages appear here after the shop is set up.'
                    : 'No pages have been shared with you yet.',
              ),
            );
          }

          return PullToRefresh(
            onRefresh: () => ref.refresh(pagesProvider.future),
            childScrolls: true,
            child: ListView(
            physics: const AlwaysScrollableScrollPhysics(),
            padding: const EdgeInsets.fromLTRB(AppSpacing.md, AppSpacing.md, AppSpacing.md, AppSpacing.xxl),
            children: [
              Text('Pages', style: Theme.of(context).textTheme.headlineLarge),
              const SizedBox(height: AppSpacing.smMd),
              TextField(
                controller: _search,
                onChanged: (_) => setState(() {}),
                decoration: const InputDecoration(
                  hintText: 'Search pages',
                  prefixIcon: Icon(Icons.search),
                ),
              ),
              const SizedBox(height: AppSpacing.md),
              if (query.isNotEmpty && filtered.isEmpty)
                Text(
                  'No pages match “$query”.',
                  style: Theme.of(context).textTheme.bodySmall,
                )
              else ...[
              if (shipped.isNotEmpty) ...[
                Text('SHIPPED WITH VELMART', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textSecondary)),
                const SizedBox(height: AppSpacing.sm),
                for (final page in shipped) ...[
                  _PageTile(page: page, role: role, system: true),
                  const SizedBox(height: AppSpacing.sm),
                ],
              ],
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  Text(
                    'BUILT BY YOU',
                    style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textSecondary),
                  ),
                  if (canCreatePage(role))
                    OutlinedButton.icon(
                      onPressed: () => context.pushNamed('pageNew'),
                      icon: const Icon(Icons.add, size: 16),
                      label: const Text('New page'),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.sm),
              if (built.isEmpty && query.isEmpty)
                Text(
                  canCreatePage(role)
                      ? 'No custom pages yet.'
                      : 'No other pages have been shared with you.',
                  style: Theme.of(context).textTheme.bodySmall,
                )
              else
                for (final page in built) ...[
                  _PageTile(page: page, role: role, system: false),
                  const SizedBox(height: AppSpacing.sm),
                ],
              ],
            ],
          ),
          );
        },
    );
  }
}

class _PageTile extends ConsumerWidget {
  const _PageTile({required this.page, required this.role, required this.system});

  final Page page;
  final UserRole role;
  final bool system;

  Future<void> _rename(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController(text: page.name);
    final newName = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename page'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Page name'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    if (newName == null || newName.isEmpty || newName == page.name || !context.mounted) return;

    try {
      await ref.read(pageRepositoryProvider).updatePage(page.id, name: newName);
      ref.invalidate(pagesProvider);
      ref.invalidate(pageSchemaProvider(page.id));
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Page renamed')));
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  Future<void> _delete(BuildContext context, WidgetRef ref) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Remove "${page.name}"?'),
        content: const Text(
          'This removes the page from your workspace. Its records are kept, not deleted, '
          'and this action is recorded in the audit log.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(
              backgroundColor: Theme.of(context).colorScheme.error,
            ),
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true || !context.mounted) return;

    try {
      await ref.read(pageRepositoryProvider).archivePage(page.id);
      ref.invalidate(pagesProvider);
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Page removed')));
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return AppCard(
      onTap: () => context.pushNamed('pageRecords', pathParameters: {'pageId': page.id}),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      child: Row(
        children: [
          Container(
            width: 36,
            height: 36,
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: system ? AppColors.brandPrimarySoft : AppColors.brandSecondarySoft,
              borderRadius: AppRadii.smRadius,
            ),
            child: Text(
              page.name.isEmpty ? '?' : page.name[0].toUpperCase(),
              style: TextStyle(
                fontWeight: FontWeight.w600,
                color: system ? AppColors.brandPrimaryDeep : AppColors.brandSecondaryDark,
              ),
            ),
          ),
          const SizedBox(width: AppSpacing.smMd),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(page.name, style: Theme.of(context).textTheme.titleMedium),
                if (page.description != null)
                  Text(page.description!, style: Theme.of(context).textTheme.bodySmall),
              ],
            ),
          ),
          if (canManageColumns(role))
            PopupMenuButton<String>(
              tooltip: 'Page actions',
              onSelected: (action) {
                switch (action) {
                  case 'columns':
                    context.pushNamed('pageColumns', pathParameters: {'pageId': page.id});
                  case 'access':
                    context.pushNamed('pageAccess', pathParameters: {'pageId': page.id});
                  case 'rename':
                    _rename(context, ref);
                  case 'delete':
                    _delete(context, ref);
                }
              },
              itemBuilder: (context) => [
                if (!page.isSystem) ...[
                  const PopupMenuItem(value: 'columns', child: Text('Edit columns')),
                  const PopupMenuItem(value: 'rename', child: Text('Rename')),
                ],
                const PopupMenuItem(value: 'access', child: Text('Manage access')),
                // System pages' schema changes only by migration (docs/API.md
                // §1.7) — no rename/delete for the six shipped tables, ever.
                if (!page.isSystem)
                  const PopupMenuItem(
                    value: 'delete',
                    child: Text('Remove page', style: TextStyle(color: AppColors.error)),
                  ),
              ],
            )
          else
            const Icon(Icons.chevron_right, color: AppColors.textDisabled),
        ],
      ),
    );
  }
}
