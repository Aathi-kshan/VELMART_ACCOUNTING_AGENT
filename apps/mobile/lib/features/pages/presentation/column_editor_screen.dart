import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../application/pages_providers.dart';
import '../domain/column.dart';
import '../domain/page.dart';
import 'widgets/column_draft_dialog.dart';

/// The Owner adds, renames, reorders, and archives columns (plan sections
/// 3.16, 10.3). System pages never reach this screen — `page_list_screen.dart`
/// doesn't offer it for `is_system` pages, since their schema changes only
/// by migration (docs/API.md section 1.7).
class ColumnEditorScreen extends ConsumerWidget {
  const ColumnEditorScreen({super.key, required this.pageId});

  final String pageId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final schemaAsync = ref.watch(pageSchemaProvider(pageId));
    return Scaffold(
      appBar: AppBar(title: const Text('Columns')),
      body: schemaAsync.when(
        data: (schema) => _ColumnEditorBody(pageId: pageId, schema: schema),
        loading: () => const AppLoadingState(),
        error: (error, _) => AppErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(pageSchemaProvider(pageId)),
        ),
      ),
    );
  }
}

class _ColumnEditorBody extends ConsumerStatefulWidget {
  const _ColumnEditorBody({required this.pageId, required this.schema});

  final String pageId;
  final PageSchema schema;

  @override
  ConsumerState<_ColumnEditorBody> createState() => _ColumnEditorBodyState();
}

class _ColumnEditorBodyState extends ConsumerState<_ColumnEditorBody> {
  bool _isBusy = false;
  String? _error;

  void _reload() => ref.invalidate(pageSchemaProvider(widget.pageId));

  ColumnDraft _draftFrom(PageColumn column) => ColumnDraft(
    name: column.name,
    dataType: column.dataType,
    isRequired: column.isRequired,
    isIndexed: column.isIndexed,
    isProtected: column.isProtected,
    options: column.options,
    defaultValue: column.defaultValue?.toString(),
    min: column.minValue,
    max: column.maxValue,
    allowNegative: column.allowNegative,
    targetPageKey: column.targetPageKey,
    displayColumn: column.displayColumn,
  );

  Future<void> _addColumn() async {
    final draft = await showColumnDraftDialog(context);
    if (draft == null) return;
    await _run(() => ref.read(pageRepositoryProvider).addColumn(widget.pageId, draft.toDefinition()));
  }

  Future<void> _editColumn(PageColumn column) async {
    final draft = await showColumnDraftDialog(context, existing: _draftFrom(column));
    if (draft == null) return;

    final typeChanged = draft.dataType != column.dataType;
    var confirmNarrow = false;

    if (typeChanged) {
      confirmNarrow = await _confirmNarrowIfNeeded(column, draft.dataType);
      if (!confirmNarrow) return; // Owner backed out after seeing the dry run.
    }

    await _run(() async {
      final result = await ref
          .read(pageRepositoryProvider)
          .updateColumn(
            column.id,
            name: draft.name,
            dataType: typeChanged ? draft.dataType : null,
            confirmNarrow: confirmNarrow,
            isRequired: draft.isRequired,
            isIndexed: draft.isIndexed,
            isProtected: draft.isProtected,
            config: draft.toDefinition().config,
          );
      if (result.removedOptionsInUse.isNotEmpty && mounted) {
        final summary = result.removedOptionsInUse.entries
            .map((e) => '${e.key} (${e.value})')
            .join(', ');
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text('Still in use on existing records: $summary')));
      }
    });
  }

  /// Runs `narrow-dry-run`, shows the Owner what would fail, and returns
  /// whether they chose to proceed (plan section 10.3 — narrowing never
  /// mutates or deletes anything; this is purely informational).
  Future<bool> _confirmNarrowIfNeeded(PageColumn column, ColumnType newType) async {
    try {
      final result = await ref.read(pageRepositoryProvider).narrowDryRun(column.id, newType);
      if (!mounted) return false;
      if (result.wouldFail == 0) return true;

      return await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Changing this column\'s type'),
              content: Text(
                '${result.wouldFail} existing record(s) hold a value that would not '
                'fit the new type. Nothing is deleted or changed by this — but new and '
                'edited records will be checked against the new type from now on. '
                'Continue?',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.of(context).pop(false),
                  child: const Text('Cancel'),
                ),
                FilledButton(
                  onPressed: () => Navigator.of(context).pop(true),
                  child: const Text('Continue'),
                ),
              ],
            ),
          ) ??
          false;
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
      return false;
    }
  }

  Future<void> _archiveColumn(PageColumn column) async {
    await _run(() => ref.read(pageRepositoryProvider).archiveColumn(column.id));
  }

  Future<void> _reorder(List<PageColumn> columns, int oldIndex, int newIndex) async {
    if (newIndex > oldIndex) newIndex -= 1;
    final reordered = List<PageColumn>.of(columns);
    final moved = reordered.removeAt(oldIndex);
    reordered.insert(newIndex, moved);

    await _run(() async {
      final repository = ref.read(pageRepositoryProvider);
      for (var i = 0; i < reordered.length; i++) {
        if (reordered[i].position != i) {
          await repository.updateColumn(reordered[i].id, position: i);
        }
      }
    });
  }

  Future<void> _run(Future<void> Function() action) async {
    setState(() {
      _isBusy = true;
      _error = null;
    });
    try {
      await action();
      _reload();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final columns = widget.schema.columns;
    return Column(
      children: [
        if (_error != null)
          MaterialBanner(
            content: Text(_error!),
            actions: [
              TextButton(onPressed: () => setState(() => _error = null), child: const Text('Dismiss')),
            ],
          ),
        if (_isBusy) const LinearProgressIndicator(),
        Expanded(
          child: ReorderableListView.builder(
            padding: const EdgeInsets.all(8),
            itemCount: columns.length,
            // ignore: deprecated_member_use
            onReorder: (oldIndex, newIndex) => _reorder(columns, oldIndex, newIndex),
            itemBuilder: (context, index) {
              final column = columns[index];
              return Card(
                key: ValueKey(column.id),
                child: ListTile(
                  title: Text(column.name),
                  subtitle: Text(
                    [
                      column.dataType.label,
                      if (column.isRequired) 'Required',
                      if (column.isIndexed) 'Indexed',
                      if (column.isProtected) 'Protected',
                    ].join(' · '),
                  ),
                  onTap: () => _editColumn(column),
                  trailing: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      IconButton(
                        icon: const Icon(Icons.archive_outlined),
                        tooltip: 'Archive column',
                        onPressed: () => _archiveColumn(column),
                      ),
                      const Icon(Icons.drag_handle),
                    ],
                  ),
                ),
              );
            },
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(16),
          child: FilledButton.icon(
            onPressed: _addColumn,
            icon: const Icon(Icons.add),
            label: const Text('Add column'),
          ),
        ),
      ],
    );
  }
}
