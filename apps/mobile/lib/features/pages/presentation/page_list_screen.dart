import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/permissions/can.dart';
import '../../../core/widgets/empty_state.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';

/// The Pages tab (plan section 22.4) — every page the caller can see. The
/// server already filters a manager down to their granted pages (plan
/// section 4.3: an ungranted page is absent, not a locked tile); this just
/// renders whatever `GET /pages` returns.
class PageListScreen extends ConsumerWidget {
  const PageListScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;
    final pages = ref.watch(pagesProvider);

    return RefreshIndicator(
      onRefresh: () => ref.refresh(pagesProvider.future),
      child: pages.when(
        data: (list) {
          if (list.isEmpty) {
            return LayoutBuilder(
              builder: (context, constraints) => SingleChildScrollView(
                physics: const AlwaysScrollableScrollPhysics(),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: constraints.maxHeight),
                  child: EmptyState(
                    icon: Icons.table_chart_outlined,
                    message: canCreatePage(role)
                        ? 'No pages yet. Tap + to build your first table.'
                        : 'No pages have been shared with you yet.',
                  ),
                ),
              ),
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(8),
            itemCount: list.length,
            separatorBuilder: (context, index) => const Divider(height: 1),
            itemBuilder: (context, index) => _PageTile(page: list[index], role: role),
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => EmptyState(
          icon: Icons.error_outline,
          message: 'Could not load pages.\n$error',
          actionLabel: 'Retry',
          onAction: () => ref.invalidate(pagesProvider),
        ),
      ),
    );
  }
}

class _PageTile extends StatelessWidget {
  const _PageTile({required this.page, required this.role});

  final Page page;
  final UserRole role;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: CircleAvatar(child: Text(page.name.isEmpty ? '?' : page.name[0].toUpperCase())),
      title: Text(page.name),
      subtitle: page.description == null ? null : Text(page.description!),
      trailing: canManageColumns(role)
          ? PopupMenuButton<String>(
              onSelected: (action) {
                switch (action) {
                  case 'columns':
                    context.pushNamed('pageColumns', pathParameters: {'pageId': page.id});
                  case 'validations':
                    context.pushNamed('pageValidations', pathParameters: {'pageId': page.id});
                  case 'access':
                    context.pushNamed('pageAccess', pathParameters: {'pageId': page.id});
                }
              },
              itemBuilder: (context) => [
                // System pages' schemas change only by migration (docs/API.md
                // section 1.7) — no column editor for the six shipped tables.
                if (!page.isSystem)
                  const PopupMenuItem(value: 'columns', child: Text('Edit columns')),
                const PopupMenuItem(value: 'validations', child: Text('Validation rules')),
                const PopupMenuItem(value: 'access', child: Text('Manage access')),
              ],
            )
          : null,
      onTap: () => context.pushNamed('pageRecords', pathParameters: {'pageId': page.id}),
    );
  }
}
