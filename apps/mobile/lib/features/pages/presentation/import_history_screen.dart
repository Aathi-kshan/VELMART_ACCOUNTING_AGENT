import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/empty_state.dart';
import '../application/pages_providers.dart';
import '../domain/csv_import.dart';

/// Recent CSV import batches for one page, with rollback while
/// `can_rollback` holds — within 24 hours of a commit that hasn't already
/// been rolled back (plan section 13.1).
class ImportHistoryScreen extends ConsumerWidget {
  const ImportHistoryScreen({super.key, required this.pageId});

  final String pageId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final batchesAsync = ref.watch(importBatchesProvider(pageId));

    return Scaffold(
      appBar: AppBar(title: const Text('Import history')),
      body: batchesAsync.when(
        data: (batches) => batches.isEmpty
            ? const EmptyState(
                icon: Icons.history,
                message: 'No CSV imports yet for this page.',
              )
            : ListView.separated(
                padding: const EdgeInsets.all(8),
                itemCount: batches.length,
                separatorBuilder: (context, index) => const Divider(height: 1),
                itemBuilder: (context, index) =>
                    _BatchTile(pageId: pageId, batch: batches[index]),
              ),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load import history.\n$error')),
      ),
    );
  }
}

class _BatchTile extends ConsumerStatefulWidget {
  const _BatchTile({required this.pageId, required this.batch});

  final String pageId;
  final ImportBatch batch;

  @override
  ConsumerState<_BatchTile> createState() => _BatchTileState();
}

class _BatchTileState extends ConsumerState<_BatchTile> {
  bool _isRollingBack = false;

  Future<void> _rollback() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Roll back this import?'),
        content: Text(
          'This soft-deletes the ${widget.batch.importedRows} row(s) it wrote. '
          'This cannot be undone.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Roll back'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    setState(() => _isRollingBack = true);
    try {
      await ref.read(pageRepositoryProvider).rollbackImport(widget.batch.id);
      ref.invalidate(importBatchesProvider(widget.pageId));
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    } finally {
      if (mounted) setState(() => _isRollingBack = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final batch = widget.batch;
    return ListTile(
      title: Text(batch.fileName),
      subtitle: Text(
        '${batch.status} · ${batch.importedRows} imported, ${batch.skippedRows} skipped '
        'of ${batch.totalRows}',
      ),
      trailing: batch.canRollback
          ? _isRollingBack
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : OutlinedButton(onPressed: _rollback, child: const Text('Roll back'))
          : null,
    );
  }
}
