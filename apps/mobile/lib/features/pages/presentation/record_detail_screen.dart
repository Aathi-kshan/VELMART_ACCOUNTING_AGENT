import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radii.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/app_status_chip.dart';
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
    final title = recordAsync.whenOrNull(
      data: (record) => ref
          .watch(pageSchemaProvider(record.pageId))
          .whenOrNull(
            data: (schema) {
              final display = schema.displayColumn;
              if (display == null) return null;
              return record.valueFor(display)?.toString();
            },
          ),
    );

    return Scaffold(
      appBar: AppBar(title: Text(title ?? 'Record')),
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
              loading: () => const AppLoadingState(),
              error: (error, _) => AppErrorState(message: '$error'),
            ),
        loading: () => const AppLoadingState(),
        error: (error, _) => AppErrorState(message: '$error'),
      ),
    );
  }
}

final _recordProvider = FutureProvider.family<PageRecord, String>((
  ref,
  recordId,
) {
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
    final role = authState is AuthAuthenticated
        ? authState.user.role
        : UserRole.manager;

    // Every field in one bordered card, rows divided by a hairline — the
    // mockup's own field-list layout, replacing what used to be a flat
    // `ListView` of separately-spaced fields.
    final fields = <Widget>[
      _DetailRow(
        label: 'Business date',
        child: Text(
          formatDate(record.businessDate),
          style: Theme.of(context).textTheme.bodyLarge,
        ),
      ),
      for (final column in schema.columns)
        _FieldValue(column: column, record: record),
    ];

    return ListView(
      padding: const EdgeInsets.all(AppSpacing.md),
      children: [
        Row(
          children: [
            AppStatusChip.recordStatus(record.status.wire),
            if (record.needsReview) ...[
              const SizedBox(width: AppSpacing.sm),
              const AppStatusChip(
                label: 'Needs review',
                tone: AppStatusTone.warning,
                icon: Icons.flag_outlined,
              ),
            ],
          ],
        ),
        const SizedBox(height: AppSpacing.md),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              for (var i = 0; i < fields.length; i++) ...[
                Padding(
                  padding: const EdgeInsets.all(AppSpacing.cardPaddingDense),
                  child: fields[i],
                ),
                if (i < fields.length - 1)
                  const Divider(height: 1, color: AppColors.hairline),
              ],
            ],
          ),
        ),
        if (canSetProtectedField(role))
          for (final column in schema.columns.where((c) => c.isProtected)) ...[
            const SizedBox(height: AppSpacing.md),
            _ChangeStatusCard(
              column: column,
              onTap: () => _changeProtectedField(context, ref, column),
            ),
          ],
        const SizedBox(height: AppSpacing.md),
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
              if (canEditRecord(role) && canDeleteRecord(role))
                const SizedBox(width: AppSpacing.smMd),
              if (canDeleteRecord(role))
                Expanded(
                  child: OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(
                      foregroundColor: AppColors.error,
                    ),
                    onPressed: () => confirmAndDeleteRecord(
                      context,
                      ref,
                      record,
                      onDeleted: onDeleted,
                    ),
                    icon: const Icon(Icons.delete_outline),
                    label: const Text('Delete'),
                  ),
                ),
            ],
          ),
        const SizedBox(height: AppSpacing.md),
        Text(
          'Every change to this record is recorded in the audit log with your name and the time.',
          textAlign: TextAlign.center,
          style: Theme.of(context).textTheme.labelMedium
              ?.copyWith(color: AppColors.textTertiary),
        ),
      ],
    );
  }

  Future<void> _changeProtectedField(
    BuildContext context,
    WidgetRef ref,
    PageColumn column,
  ) async {
    final current = record.valueFor(column) as String?;
    final selected = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              0,
              AppSpacing.md,
              AppSpacing.md,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Change ${column.name}',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: AppSpacing.sm),
                for (final option in column.options)
                  ListTile(
                    title: Text(option),
                    selected: option == current,
                    selectedTileColor: AppColors.brandPrimarySoft,
                    trailing: option == current
                        ? const Icon(
                            Icons.check,
                            color: AppColors.brandPrimaryDeep,
                          )
                        : null,
                    onTap: () => Navigator.of(context).pop(option),
                  ),
              ],
            ),
          ),
        );
      },
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
    }
  }
}

/// Shared by the detail screen and the desktop record table.
Future<bool> confirmAndDeleteRecord(
  BuildContext context,
  WidgetRef ref,
  PageRecord record, {
  VoidCallback? onDeleted,
}) async {
  var typed = '';
  final reason = await showDialog<String>(
    context: context,
    builder: (context) => AlertDialog(
      title: const Text('Void this record?'),
      content: TextField(
        decoration: const InputDecoration(labelText: 'Reason (required)'),
        autofocus: true,
        onChanged: (value) => typed = value,
      ),
      actions: [
        TextButton(onPressed: () => context.pop(), child: const Text('Cancel')),
        FilledButton(
          style: FilledButton.styleFrom(backgroundColor: AppColors.error),
          onPressed: () => context.pop(typed.trim()),
          child: const Text('Delete'),
        ),
      ],
    ),
  );
  if (reason == null || reason.isEmpty || !context.mounted) return false;

  try {
    await ref
        .read(pageRepositoryProvider)
        .deleteRecord(record.id, reason: reason);
    ref.read(recordListControllerProvider(record.pageId).notifier).refresh();
    ref.invalidate(recordSummaryProvider(record.pageId));
    onDeleted?.call();
    return true;
  } on ApiException catch (e) {
    if (context.mounted) {
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
    }
    return false;
  }
}

/// One label+value row inside the field-list card — the same shape
/// `_FieldValue` renders for a schema column, reused for the fixed
/// "Business date" row above it so every row in the card looks identical.
class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.child});

  final String label;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        const SizedBox(height: AppSpacing.xs),
        child,
      ],
    );
  }
}

/// A protected column's change trigger (design.md §25.5, §32 "Protected
/// field"): amber, with the lock explanation up front — replaces what used
/// to be a plain `OutlinedButton` with no context about *why* this is a
/// separate action from Edit.
class _ChangeStatusCard extends StatelessWidget {
  const _ChangeStatusCard({required this.column, required this.onTap});

  final PageColumn column;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Material(
      color: AppColors.warningSoft,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadii.mdRadius,
        side: const BorderSide(color: AppColors.warningBorder),
      ),
      child: InkWell(
        onTap: onTap,
        borderRadius: AppRadii.mdRadius,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            children: [
              const Icon(
                Icons.lock_outline,
                color: AppColors.warningText,
                size: 20,
              ),
              const SizedBox(width: AppSpacing.smMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Change ${column.name}',
                      style: textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w600,
                        color: AppColors.textPrimary,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      'Only an Owner can change this value.',
                      style: textTheme.bodySmall?.copyWith(
                        color: AppColors.textSecondary,
                      ),
                    ),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right, color: AppColors.textTertiary),
            ],
          ),
        ),
      ),
    );
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
    } else if (column.dataType == ColumnType.select ||
        column.dataType == ColumnType.multiSelect) {
      final items = value is List
          ? value.cast<String>()
          : (value == null ? const <String>[] : <String>['$value']);
      valueWidget = items.isEmpty
          ? Text(
              '—',
              style: valueStyle?.copyWith(color: Theme.of(context).hintColor),
            )
          : Wrap(
              spacing: AppSpacing.xs,
              children: items
                  .map((item) => AppStatusChip.recordStatus(item))
                  .toList(),
            );
    } else if (value == null || (value is String && value.isEmpty)) {
      valueWidget = Text(
        '—',
        style: valueStyle?.copyWith(color: Theme.of(context).hintColor),
      );
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
