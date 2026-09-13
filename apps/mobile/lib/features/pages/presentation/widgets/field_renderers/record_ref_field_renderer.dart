import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../application/pages_providers.dart';
import '../../../application/record_list_controller.dart';
import '../../../domain/column.dart';
import '../../../domain/page.dart';

/// RECORD_REF, STORE_REF, USER_REF (plan sections 10.2, 11.2). All three are
/// "pick an existing row and store its id" — they differ only in where the
/// options come from. The picker shows the target's `display_column` (or
/// name), never the raw uuid (plan section 11.2).
class RecordRefFieldRenderer extends ConsumerWidget {
  const RecordRefFieldRenderer({
    super.key,
    required this.column,
    required this.value,
    required this.onChanged,
    this.enabled = true,
    this.errorText,
  });

  final PageColumn column;
  final String? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;
  final String? errorText;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    switch (column.dataType) {
      case ColumnType.storeRef:
        return ref
            .watch(storesProvider)
            .when(
              data: (list) => _Picker(
                column: column,
                value: value,
                onChanged: onChanged,
                enabled: enabled,
                errorText: errorText,
                options: {for (final s in list) s.id: s.name},
              ),
              loading: () => const _PickerPlaceholder(loading: true),
              error: (_, _) => const _PickerPlaceholder(message: 'No stores available'),
            );
      case ColumnType.userRef:
        return ref
            .watch(usersProvider)
            .when(
              data: (list) => _Picker(
                column: column,
                value: value,
                onChanged: onChanged,
                enabled: enabled,
                errorText: errorText,
                options: {for (final u in list) u.id: u.fullName},
              ),
              loading: () => const _PickerPlaceholder(loading: true),
              // A manager's own GET /users call 403s — owner-only by plan
              // section 4.2. Degrade to showing the stored id rather than a
              // dead picker (see the P3 plan's "known limitations").
              error: (_, _) => _ReadOnlyIdField(column: column, value: value),
            );
      case ColumnType.recordRef:
        final targetKey = column.targetPageKey;
        if (targetKey == null) {
          return const _PickerPlaceholder(
            message: 'This link has no target page configured',
          );
        }
        return ref
            .watch(pagesProvider)
            .when(
              data: (pages) {
                Page? target;
                for (final candidate in pages) {
                  if (candidate.key == targetKey) {
                    target = candidate;
                    break;
                  }
                }
                if (target == null) {
                  return const _PickerPlaceholder(message: 'Linked page not found');
                }
                return _RecordRefOptions(
                  targetPage: target,
                  column: column,
                  value: value,
                  onChanged: onChanged,
                  enabled: enabled,
                  errorText: errorText,
                );
              },
              loading: () => const _PickerPlaceholder(loading: true),
              error: (_, _) => const _PickerPlaceholder(message: 'Linked page not found'),
            );
      default:
        throw StateError('${column.dataType} is not a reference column type');
    }
  }
}

/// Loads the target page's records to populate a RECORD_REF picker.
class _RecordRefOptions extends ConsumerWidget {
  const _RecordRefOptions({
    required this.targetPage,
    required this.column,
    required this.value,
    required this.onChanged,
    required this.enabled,
    required this.errorText,
  });

  final Page targetPage;
  final PageColumn column;
  final String? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;
  final String? errorText;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(recordListControllerProvider(targetPage.id));
    if (state.isLoading && state.items.isEmpty) {
      return const _PickerPlaceholder(loading: true);
    }

    // The column's own `display_column` override wins; with none configured,
    // fall back to the target page's own heuristic (its first text-ish
    // column) rather than showing the raw record id (plan section 11.2/P4 §10).
    // The heuristic needs the target's columns, which `Page` alone doesn't
    // carry — fetch its schema too, degrading to no fallback while it loads.
    final targetSchema = ref.watch(pageSchemaProvider(targetPage.id)).valueOrNull;
    final displayKey = column.displayColumn ?? targetSchema?.displayColumn?.key;
    final options = <String, String>{
      for (final record in state.items)
        record.id: (displayKey != null ? record.data[displayKey] : null)?.toString() ??
            record.id,
    };

    return _Picker(
      column: column,
      value: value,
      onChanged: onChanged,
      enabled: enabled,
      errorText: errorText,
      options: options,
    );
  }
}

class _Picker extends StatelessWidget {
  const _Picker({
    required this.column,
    required this.value,
    required this.onChanged,
    required this.enabled,
    required this.errorText,
    required this.options,
  });

  final PageColumn column;
  final String? value;
  final ValueChanged<Object?> onChanged;
  final bool enabled;
  final String? errorText;
  final Map<String, String> options;

  @override
  Widget build(BuildContext context) {
    return DropdownButtonFormField<String>(
      initialValue: options.containsKey(value) ? value : null,
      decoration: InputDecoration(
        labelText: column.name,
        border: const OutlineInputBorder(),
        errorText: errorText,
        helperText: column.description,
      ),
      items: options.entries
          .map((e) => DropdownMenuItem(value: e.key, child: Text(e.value)))
          .toList(),
      onChanged: enabled ? (next) => onChanged(next) : null,
      validator: (input) {
        if (column.isRequired && input == null) {
          return '${column.name} is required';
        }
        return null;
      },
    );
  }
}

class _PickerPlaceholder extends StatelessWidget {
  const _PickerPlaceholder({this.loading = false, this.message});

  final bool loading;
  final String? message;

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: LinearProgressIndicator(),
      );
    }
    return Text(
      message ?? 'Unavailable',
      style: TextStyle(color: Theme.of(context).colorScheme.error),
    );
  }
}

class _ReadOnlyIdField extends StatelessWidget {
  const _ReadOnlyIdField({required this.column, required this.value});

  final PageColumn column;
  final String? value;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      initialValue: value ?? '',
      enabled: false,
      decoration: InputDecoration(
        labelText: column.name,
        border: const OutlineInputBorder(),
        helperText: 'Only the Owner can browse this list',
      ),
    );
  }
}
