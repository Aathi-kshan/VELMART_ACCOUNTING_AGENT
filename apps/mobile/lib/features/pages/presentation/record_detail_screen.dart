import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/widgets/amount_text.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../application/record_list_controller.dart';
import '../domain/column.dart';
import '../domain/page.dart';
import '../domain/record.dart';

/// One record, read-only, with Edit/Delete gated by `can.dart` (plan section
/// 3.7). A manager never sees Edit or Delete — they cannot edit records at
/// all (docs/API.md section 5: `MANAGER_CANNOT_EDIT`).
class RecordDetailScreen extends ConsumerWidget {
  const RecordDetailScreen({super.key, required this.recordId});

  final String recordId;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final recordAsync = ref.watch(_recordProvider(recordId));

    return Scaffold(
      appBar: AppBar(title: const Text('Record')),
      body: recordAsync.when(
        data: (record) => ref
            .watch(pageSchemaProvider(record.pageId))
            .when(
              data: (schema) => RecordDetailView(
                record: record,
                schema: schema,
                onEdit: () => context.pushNamed(
                  'recordEdit',
                  pathParameters: {'recordId': record.id},
                ),
                onDeleted: () => context.pop(),
              ),
              loading: () => const Center(child: CircularProgressIndicator()),
              error: (error, _) => Center(child: Text('Could not load this page.\n$error')),
            ),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load this record.\n$error')),
      ),
    );
  }
}

final _recordProvider = FutureProvider.family<PageRecord, String>((ref, recordId) {
  return ref.watch(pageRepositoryProvider).getRecord(recordId);
});

/// The record's fields, rendered read-only — reused both by the pushed
/// [RecordDetailScreen] and inline in the master-detail layout of
/// `record_list_screen.dart`.
class RecordDetailView extends ConsumerWidget {
  const RecordDetailView({
    super.key,
    required this.record,
    required this.schema,
    this.onEdit,
    this.onDeleted,
  });

  final PageRecord record;
  final PageSchema schema;
  final VoidCallback? onEdit;
  final VoidCallback? onDeleted;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (record.needsReview)
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: const ListTile(
              leading: Icon(Icons.flag_outlined),
              title: Text('Needs review'),
              subtitle: Text('A validation rule flagged this record for a second look.'),
            ),
          ),
        Text('Business date', style: Theme.of(context).textTheme.labelMedium),
        Text(formatDate(record.businessDate), style: Theme.of(context).textTheme.bodyLarge),
        const SizedBox(height: 16),
        for (final column in schema.columns) ...[
          _FieldValue(column: column, record: record),
          const SizedBox(height: 16),
        ],
        // The only way a protected value ever changes (plan section 11.4) —
        // not through the generic Edit form above, which never submits a
        // protected column's value at all (see `PageSchema.writableColumns`).
        if (canSetProtectedField(role))
          for (final column in schema.columns.where((c) => c.isProtected)) ...[
            OutlinedButton.icon(
              onPressed: () => _changeProtectedField(context, ref, column),
              icon: const Icon(Icons.edit_note),
              label: Text('Change ${column.name}'),
            ),
            const SizedBox(height: 8),
          ],
        const SizedBox(height: 8),
        if (canEditRecord(role) || canDeleteRecord(role))
          Row(
            children: [
              if (canEditRecord(role))
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: onEdit,
                    icon: const Icon(Icons.edit_outlined),
                    label: const Text('Edit'),
                  ),
                ),
              if (canEditRecord(role) && canDeleteRecord(role)) const SizedBox(width: 12),
              if (canDeleteRecord(role))
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: Theme.of(context).colorScheme.error,
                    ),
                    onPressed: () => _confirmDelete(context, ref),
                    icon: const Icon(Icons.delete_outline),
                    label: const Text('Delete'),
                  ),
                ),
            ],
          ),
      ],
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final reasonController = TextEditingController();
    final reason = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this record?'),
        content: TextField(
          controller: reasonController,
          decoration: const InputDecoration(
            labelText: 'Reason (required)',
            border: OutlineInputBorder(),
          ),
          autofocus: true,
        ),
        actions: [
          TextButton(onPressed: () => context.pop(), child: const Text('Cancel')),
          FilledButton(
            onPressed: () => context.pop(reasonController.text.trim()),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (reason == null || reason.isEmpty || !context.mounted) return;

    try {
      await ref.read(pageRepositoryProvider).deleteRecord(record.id, reason: reason);
      // Unlike create/update (`record_form_screen.dart`'s `_submit`), nothing
      // else re-fetches the page's record list after a delete — without this,
      // the deleted row stays visible until some other refresh happens,
      // making a successful delete look like it silently did nothing.
      ref.read(recordListControllerProvider(record.pageId).notifier).refresh();
      onDeleted?.call();
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }

  Future<void> _changeProtectedField(
    BuildContext context,
    WidgetRef ref,
    PageColumn column,
  ) async {
    final current = record.valueFor(column) as String?;
    final selected = await showDialog<String>(
      context: context,
      builder: (context) => SimpleDialog(
        title: Text('Change ${column.name}'),
        children: [
          for (final option in column.options)
            RadioListTile<String>(
              title: Text(option),
              value: option,
              // ignore: deprecated_member_use
              groupValue: current,
              // ignore: deprecated_member_use
              onChanged: (value) => Navigator.of(context).pop(value),
            ),
        ],
      ),
    );
    if (selected == null || selected == current || !context.mounted) return;

    try {
      await ref
          .read(pageRepositoryProvider)
          .setProtectedField(
            record.id,
            columnKey: column.key,
            value: selected,
            version: record.version,
          );
      ref.invalidate(_recordProvider(record.id));
    } on ApiException catch (e) {
      if (!context.mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }
}

class _FieldValue extends StatelessWidget {
  const _FieldValue({required this.column, required this.record});

  final PageColumn column;
  final PageRecord record;

  @override
  Widget build(BuildContext context) {
    final value = record.valueFor(column);
    final labelStyle = Theme.of(context).textTheme.labelMedium;
    final valueStyle = Theme.of(context).textTheme.bodyLarge;

    Widget valueWidget;
    if (column.dataType == ColumnType.currency) {
      valueWidget = AmountText(value, style: valueStyle, colorByValue: true);
    } else if (column.dataType == ColumnType.date) {
      valueWidget = Text(formatDate(value), style: valueStyle);
    } else if (column.dataType == ColumnType.datetime) {
      valueWidget = Text(formatDateTime(value), style: valueStyle);
    } else if (column.dataType == ColumnType.boolean) {
      valueWidget = Text(value == true ? 'Yes' : 'No', style: valueStyle);
    } else if (column.dataType == ColumnType.multiSelect) {
      final items = (value is List ? value.cast<String>() : const <String>[]);
      valueWidget = Wrap(
        spacing: 4,
        children: items.map((item) => Chip(label: Text(item))).toList(),
      );
    } else if (value == null || (value is String && value.isEmpty)) {
      valueWidget = Text('—', style: valueStyle?.copyWith(color: Theme.of(context).hintColor));
    } else {
      valueWidget = Text('$value', style: valueStyle);
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(column.name, style: labelStyle),
        const SizedBox(height: 2),
        valueWidget,
      ],
    );
  }
}
