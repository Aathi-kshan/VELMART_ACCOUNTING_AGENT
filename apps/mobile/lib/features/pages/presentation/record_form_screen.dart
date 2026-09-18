import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/adaptive_scaffold.dart';
import '../../../core/widgets/app_conflict_state.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../application/record_list_controller.dart';
import '../domain/page.dart';
import '../domain/record.dart';
import 'widgets/field_renderers/field_renderer.dart';

/// The dynamic form (plan section 3.13) — fields built from `PageSchema`
/// through [FieldRenderer], one widget per column type. Adding a column on
/// the server changes this form on the next load with no app release (plan
/// section 10.4).
///
/// Create sends a fresh `Idempotency-Key`; edit sends `If-Match: version`
/// (`PageRepository` does both). A 422 lands the server's own message under
/// the right field (`ApiException.fieldErrors`); a 409 `VERSION_CONFLICT`
/// means someone else changed this record first — reload rather than
/// silently overwrite them.
class RecordFormScreen extends ConsumerStatefulWidget {
  const RecordFormScreen({super.key, this.pageId, this.recordId})
    : assert(
        (pageId != null) != (recordId != null),
        'Pass exactly one of pageId (create) or recordId (edit).',
      );

  /// Create mode: which page this new record belongs to.
  final String? pageId;

  /// Edit mode: which record to load and update.
  final String? recordId;

  bool get isEdit => recordId != null;

  @override
  ConsumerState<RecordFormScreen> createState() => _RecordFormScreenState();
}

class _RecordFormScreenState extends ConsumerState<RecordFormScreen> {
  final _formKey = GlobalKey<FormState>();
  final Map<String, Object?> _values = {};

  DateTime _occurredAt = DateTime.now();
  String? _storeId;
  int? _version;
  bool _initialized = false;
  bool _isSubmitting = false;
  Map<String, String> _fieldErrors = {};
  String? _generalError;

  @override
  Widget build(BuildContext context) {
    if (widget.isEdit) {
      return ref
          .watch(_recordProvider(widget.recordId!))
          .when(
            data: (record) => ref
                .watch(pageSchemaProvider(record.pageId))
                .when(
                  data: (schema) => _scaffold(context, schema, record),
                  loading: () => _loadingScaffold('Edit record'),
                  error: (error, _) => _errorScaffold('Edit record', error),
                ),
            loading: () => _loadingScaffold('Edit record'),
            error: (error, _) => _errorScaffold('Edit record', error),
          );
    }

    return ref
        .watch(pageSchemaProvider(widget.pageId!))
        .when(
          data: (schema) => _scaffold(context, schema, null),
          loading: () => _loadingScaffold('New record'),
          error: (error, _) => _errorScaffold('New record', error),
        );
  }

  Widget _loadingScaffold(String title) => Scaffold(
    appBar: AppBar(title: Text(title)),
    body: const AppLoadingState(),
  );

  Widget _errorScaffold(String title, Object error) => Scaffold(
    appBar: AppBar(title: Text(title)),
    body: AppErrorState(message: '$error'),
  );

  void _initializeOnce(PageSchema schema, PageRecord? record) {
    if (_initialized) return;
    _initialized = true;
    if (record != null) {
      _values.addAll(record.data);
      _occurredAt = parseWireDateTime(record.occurredAt) ?? DateTime.now();
      _storeId = record.storeId;
      _version = record.version;
    } else {
      for (final column in schema.writableColumns) {
        final defaultValue = column.defaultValue;
        if (defaultValue != null) _values[column.key] = defaultValue;
      }
    }
  }

  Widget _scaffold(
    BuildContext context,
    PageSchema schema,
    PageRecord? record,
  ) {
    _initializeOnce(schema, record);
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated
        ? authState.user.role
        : UserRole.manager;
    final showStorePicker = schema.page.storeColumnKey == null;

    return Scaffold(
      appBar: AppBar(
        title: Text(
          widget.isEdit ? 'Edit ${schema.page.name}' : schema.page.name,
        ),
      ),
      body: SafeArea(
        child: Align(
          alignment: Alignment.topCenter,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth:
                  AdaptiveScaffold.isCompact(MediaQuery.sizeOf(context).width)
                  ? double.infinity
                  : 720,
            ),
            child: Column(
              children: [
                Expanded(
                  child: Form(
                    key: _formKey,
                    child: ListView(
                      key: ValueKey(
                        'record-fields-${record?.id}-${_version ?? 0}',
                      ),
                      padding: const EdgeInsets.all(AppSpacing.md),
                      children: [
                        if (_generalError != null) ...[
                          Card(
                            color: AppColors.errorSoft,
                            child: Padding(
                              padding: const EdgeInsets.all(AppSpacing.smMd),
                              child: Text(
                                _generalError!,
                                style: Theme.of(context).textTheme.bodyLarge
                                    ?.copyWith(color: AppColors.error),
                              ),
                            ),
                          ),
                          const SizedBox(height: AppSpacing.md),
                        ],
                        _OccurredAtField(
                          value: _occurredAt,
                          onChanged: (next) =>
                              setState(() => _occurredAt = next),
                        ),
                        const SizedBox(height: AppSpacing.md),
                        if (showStorePicker) ...[
                          _StorePicker(
                            storeId: _storeId,
                            onChanged: (next) =>
                                setState(() => _storeId = next),
                          ),
                          const SizedBox(height: AppSpacing.md),
                        ],
                        for (final column in schema.columns) ...[
                          FieldRenderer(
                            column: column,
                            value: _values[column.key],
                            role: role,
                            enabled: !schema.generatedColumns.contains(
                              column.key,
                            ),
                            errorText: _fieldErrors[column.key],
                            onChanged: (next) =>
                                setState(() => _values[column.key] = next),
                          ),
                          const SizedBox(height: AppSpacing.md),
                        ],
                      ],
                    ),
                  ),
                ),
                const Divider(height: 1),
                Padding(
                  padding: const EdgeInsets.fromLTRB(
                    AppSpacing.md,
                    AppSpacing.smMd,
                    AppSpacing.md,
                    AppSpacing.md,
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _isSubmitting ? null : () => context.pop(),
                          child: const Text('Cancel'),
                        ),
                      ),
                      const SizedBox(width: AppSpacing.smMd),
                      Expanded(
                        child: FilledButton(
                          onPressed: _isSubmitting
                              ? null
                              : () => _submit(schema, record),
                          child: _isSubmitting
                              ? const SizedBox(
                                  width: 20,
                                  height: 20,
                                  child: CircularProgressIndicator(
                                    strokeWidth: 2,
                                    color: Colors.white,
                                  ),
                                )
                              : const Text('Save'),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _submit(PageSchema schema, PageRecord? existing) async {
    if (!(_formKey.currentState?.validate() ?? false)) return;

    setState(() {
      _isSubmitting = true;
      _fieldErrors = {};
      _generalError = null;
    });

    final data = <String, Object?>{
      for (final column in schema.writableColumns)
        if (_values.containsKey(column.key)) column.key: _values[column.key],
    };

    final repository = ref.read(pageRepositoryProvider);
    try {
      if (widget.isEdit) {
        await repository.updateRecord(
          existing!.id,
          version: _version!,
          occurredAt: toWireDateTime(_occurredAt),
          storeId: _storeId,
          data: data,
        );
      } else {
        await repository.createRecord(
          schema.page.id,
          occurredAt: toWireDateTime(_occurredAt),
          storeId: _storeId,
          data: data,
        );
      }
      ref.read(recordListControllerProvider(schema.page.id).notifier).refresh();
      ref.invalidate(recordSummaryProvider(schema.page.id));
      if (mounted) context.pop();
    } on ApiException catch (e) {
      if (!mounted) return;
      if (e.isVersionConflict) {
        await _handleVersionConflict(e);
      } else if (e.isValidationFailure) {
        setState(() {
          _fieldErrors = e.fieldErrors;
          _generalError = e.fieldErrors.isEmpty ? e.detail : null;
        });
      } else {
        setState(() => _generalError = e.detail);
      }
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  Future<void> _handleVersionConflict(ApiException e) async {
    if (!mounted) return;
    await AppConflictState.presentDialog(
      context,
      onReload: () {
        if (widget.recordId == null) return;
        ref.invalidate(_recordProvider(widget.recordId!));
        setState(() {
          _initialized = false;
          _values.clear();
        });
      },
    );
  }
}

final _recordProvider = FutureProvider.family<PageRecord, String>((
  ref,
  recordId,
) {
  return ref.watch(pageRepositoryProvider).getRecord(recordId);
});

class _OccurredAtField extends StatelessWidget {
  const _OccurredAtField({required this.value, required this.onChanged});

  final DateTime value;
  final ValueChanged<DateTime> onChanged;

  Future<void> _pick(BuildContext context) async {
    final date = await showDatePicker(
      context: context,
      initialDate: value,
      firstDate: DateTime(value.year - 10),
      lastDate: DateTime(value.year + 10),
    );
    if (date == null || !context.mounted) return;

    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(value),
    );
    if (time == null) return;

    onChanged(
      DateTime(date.year, date.month, date.day, time.hour, time.minute),
    );
  }

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      key: ValueKey('occurred_at-$value'),
      readOnly: true,
      initialValue: formatDateTime(toWireDateTime(value)),
      decoration: const InputDecoration(
        labelText: 'When did this happen? *',
        suffixIcon: Icon(Icons.event),
      ),
      onTap: () => _pick(context),
    );
  }
}

class _StorePicker extends ConsumerWidget {
  const _StorePicker({required this.storeId, required this.onChanged});

  final String? storeId;
  final ValueChanged<String?> onChanged;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return ref
        .watch(storesProvider)
        .when(
          data: (stores) {
            if (stores.isEmpty) return const SizedBox.shrink();
            return DropdownButtonFormField<String>(
              initialValue: stores.any((s) => s.id == storeId) ? storeId : null,
              decoration: const InputDecoration(labelText: 'Store'),
              items: [
                const DropdownMenuItem(value: null, child: Text('(none)')),
                for (final store in stores)
                  DropdownMenuItem(value: store.id, child: Text(store.name)),
              ],
              onChanged: onChanged,
            );
          },
          loading: () => const LinearProgressIndicator(),
          error: (_, _) => const SizedBox.shrink(),
        );
  }
}
