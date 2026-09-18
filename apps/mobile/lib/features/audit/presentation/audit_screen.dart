import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/refreshable.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/audit_providers.dart';
import '../domain/audit_log_entry.dart';

/// The Owner-facing audit log (plan section 18.3, P5): plain sentences,
/// grouped under a "Today"/"Yesterday"/date header, filterable, exportable
/// by the Owner. A manager sees the same feed, already narrowed server-side
/// to pages they can view (`app/services/audit_read_service.py`) — this
/// screen renders whatever comes back, same as every other 🟡 filtered list.
class AuditScreen extends ConsumerStatefulWidget {
  const AuditScreen({super.key});

  @override
  ConsumerState<AuditScreen> createState() => _AuditScreenState();
}

class _AuditScreenState extends ConsumerState<AuditScreen> {
  bool _isExporting = false;

  Future<void> _export() async {
    if (_isExporting) return;
    setState(() => _isExporting = true);
    try {
      final filters = ref.read(auditLogFiltersProvider);
      final bytes = await ref.read(auditRepositoryProvider).exportAuditLogs(filters: filters);
      await Share.shareXFiles([
        XFile.fromData(bytes, name: 'audit-log.csv', mimeType: 'text/csv'),
      ]);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    } finally {
      if (mounted) setState(() => _isExporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;
    final state = ref.watch(auditLogControllerProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Audit log'),
        actions: [
          if (canExportAuditLog(role))
            IconButton(
              icon: _isExporting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.file_download_outlined),
              tooltip: 'Export audit log',
              onPressed: _isExporting ? null : _export,
            ),
        ],
      ),
      body: PullToRefresh(
        onRefresh: () => ref.read(auditLogControllerProvider.notifier).refresh(),
        childScrolls: state.items.isNotEmpty,
        child: _body(state),
      ),
    );
  }

  Widget _body(AuditLogState state) {
    if (state.isLoading && state.items.isEmpty) {
      return const AppLoadingState();
    }
    if (state.error != null && state.items.isEmpty) {
      return AppErrorState(
        message: state.error!.detail,
        onRetry: () => ref.read(auditLogControllerProvider.notifier).refresh(),
      );
    }
    if (state.items.isEmpty) {
      return const EmptyState(icon: Icons.history, message: 'No activity yet.');
    }

    final grouped = _groupByDateHeader(state.items);
    return ListView.builder(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.symmetric(vertical: 8),
      itemCount: grouped.length + (state.hasMore ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == grouped.length) {
          return Padding(
            padding: const EdgeInsets.all(16),
            child: Center(
              child: state.isLoadingMore
                  ? const CircularProgressIndicator()
                  : TextButton(
                      onPressed: () => ref.read(auditLogControllerProvider.notifier).loadMore(),
                      child: const Text('Load more'),
                    ),
            ),
          );
        }
        final section = grouped[index];
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.fromLTRB(AppSpacing.md, AppSpacing.smMd, AppSpacing.md, AppSpacing.xs),
              child: Text(
                section.header,
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
            for (final entry in section.entries) _EntryTile(entry: entry),
          ],
        );
      },
    );
  }
}

class _DateSection {
  const _DateSection(this.header, this.entries);

  final String header;
  final List<AuditLogEntry> entries;
}

List<_DateSection> _groupByDateHeader(List<AuditLogEntry> items) {
  final sections = <_DateSection>[];
  for (final entry in items) {
    if (sections.isNotEmpty && sections.last.header == entry.dateHeader) {
      sections.last.entries.add(entry);
    } else {
      sections.add(_DateSection(entry.dateHeader, [entry]));
    }
  }
  return sections;
}

class _EntryTile extends StatelessWidget {
  const _EntryTile({required this.entry});

  final AuditLogEntry entry;

  @override
  Widget build(BuildContext context) {
    final time = TimeOfDay.fromDateTime(entry.createdAt).format(context);
    return ListTile(
      dense: true,
      leading: SizedBox(
        width: 48,
        child: Text(time, style: Theme.of(context).textTheme.bodySmall),
      ),
      title: Text(entry.sentence),
      onTap: (entry.oldData != null || entry.newData != null)
          ? () => _showDetail(context, entry)
          : null,
    );
  }

  void _showDetail(BuildContext context, AuditLogEntry entry) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(entry.action),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (entry.oldData != null) ...[
                const Text('Before', style: TextStyle(fontWeight: FontWeight.bold)),
                Text(entry.oldData.toString()),
                const SizedBox(height: 12),
              ],
              if (entry.newData != null) ...[
                const Text('After', style: TextStyle(fontWeight: FontWeight.bold)),
                Text(entry.newData.toString()),
              ],
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }
}
