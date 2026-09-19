import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../application/pages_providers.dart';
import '../../domain/column.dart';

/// A column definition still being edited by the Owner, before it becomes a
/// [ColumnDefinition] sent to the server. Mutable on purpose — the dialog
/// below edits one of these in place.
class ColumnDraft {
  ColumnDraft({
    required this.name,
    required this.dataType,
    this.isRequired = false,
    this.isIndexed = false,
    this.isProtected = false,
    this.options = const [],
    this.defaultValue,
    this.min,
    this.max,
    this.allowNegative = false,
    this.targetPageKey,
    this.displayColumn,
  });

  String name;
  ColumnType dataType;
  bool isRequired;
  bool isIndexed;
  bool isProtected;
  List<String> options;
  String? defaultValue;
  String? min;
  String? max;
  bool allowNegative;
  String? targetPageKey;
  String? displayColumn;

  ColumnDraft copy() => ColumnDraft(
    name: name,
    dataType: dataType,
    isRequired: isRequired,
    isIndexed: isIndexed,
    isProtected: isProtected,
    options: List.of(options),
    defaultValue: defaultValue,
    min: min,
    max: max,
    allowNegative: allowNegative,
    targetPageKey: targetPageKey,
    displayColumn: displayColumn,
  );

  /// Builds the `config` map exactly as `app/schemas/column.py` expects it
  /// (plan section 8.3).
  ColumnDefinition toDefinition() {
    final config = <String, dynamic>{};
    if (dataType.needsOptions) config['options'] = options;
    if (defaultValue != null && defaultValue!.isNotEmpty) config['default'] = defaultValue;
    if (dataType == ColumnType.number || dataType == ColumnType.percent) {
      if (min != null && min!.isNotEmpty) config['min'] = min;
      if (max != null && max!.isNotEmpty) config['max'] = max;
    }
    if (dataType == ColumnType.currency) {
      config['allow_negative'] = allowNegative;
      if (min != null && min!.isNotEmpty) config['min'] = min;
    }
    if (dataType == ColumnType.recordRef) {
      if (targetPageKey != null) config['target_page_key'] = targetPageKey;
      if (displayColumn != null) config['display_column'] = displayColumn;
    }
    return ColumnDefinition(
      name: name,
      dataType: dataType,
      isRequired: isRequired,
      isIndexed: isIndexed,
      isProtected: isProtected,
      config: config,
    );
  }
}

/// The column-authoring dialog shared by the page builder (new columns
/// inline) and the column editor (adding a column to an existing page).
Future<ColumnDraft?> showColumnDraftDialog(
  BuildContext context, {
  ColumnDraft? existing,
}) {
  return showDialog<ColumnDraft>(
    context: context,
    builder: (context) => _ColumnDraftDialog(draft: existing?.copy() ?? ColumnDraft(name: '', dataType: ColumnType.text)),
  );
}

class _ColumnDraftDialog extends ConsumerStatefulWidget {
  const _ColumnDraftDialog({required this.draft});

  final ColumnDraft draft;

  @override
  ConsumerState<_ColumnDraftDialog> createState() => _ColumnDraftDialogState();
}

class _ColumnDraftDialogState extends ConsumerState<_ColumnDraftDialog> {
  final _formKey = GlobalKey<FormState>();
  late final _nameController = TextEditingController(text: widget.draft.name);
  late final _optionsController = TextEditingController(text: widget.draft.options.join(', '));
  late final _defaultController = TextEditingController(text: widget.draft.defaultValue ?? '');
  late final _minController = TextEditingController(text: widget.draft.min ?? '');
  late final _maxController = TextEditingController(text: widget.draft.max ?? '');
  late ColumnType _dataType = widget.draft.dataType;
  late bool _isRequired = widget.draft.isRequired;
  late bool _isIndexed = widget.draft.isIndexed;
  late bool _isProtected = widget.draft.isProtected;
  late bool _allowNegative = widget.draft.allowNegative;
  String? _targetPageKey;
  String? _displayColumn;

  @override
  void initState() {
    super.initState();
    _targetPageKey = widget.draft.targetPageKey;
    _displayColumn = widget.draft.displayColumn;
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(widget.draft.name.isEmpty ? 'Add column' : 'Edit column'),
      content: SizedBox(
        width: 420,
        child: Form(
          key: _formKey,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                TextFormField(
                  controller: _nameController,
                  decoration: const InputDecoration(labelText: 'Column name'),
                  validator: (input) =>
                      (input == null || input.trim().isEmpty) ? 'Required' : null,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<ColumnType>(
                  initialValue: _dataType,
                  decoration: const InputDecoration(labelText: 'Type'),
                  items: [
                    for (final type in ColumnType.selectableForNewColumn)
                      DropdownMenuItem(value: type, child: Text(type.label)),
                  ],
                  onChanged: (next) => setState(() => _dataType = next ?? _dataType),
                ),
                const SizedBox(height: 8),
                if (!_dataType.isReadOnly)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Required'),
                    value: _isRequired,
                    onChanged: (next) => setState(() => _isRequired = next ?? false),
                  ),
                if (_dataType.isIndexable)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Index for fast filtering/sorting'),
                    subtitle: const Text('A page allows at most 4 indexed numeric and 2 indexed date columns'),
                    value: _isIndexed,
                    onChanged: (next) => setState(() => _isIndexed = next ?? false),
                  ),
                if (_dataType.supportsProtection)
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Protected'),
                    subtitle: const Text('Only the Owner can set or change this value'),
                    value: _isProtected,
                    onChanged: (next) => setState(() => _isProtected = next ?? false),
                  ),
                if (_dataType.needsOptions) ...[
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _optionsController,
                    decoration: const InputDecoration(
                      labelText: 'Options (comma separated)',
                      helperText: 'e.g. Electricity, Rent, Transport',
                    ),
                    validator: (input) {
                      if (_dataType.needsOptions &&
                          (input == null ||
                              input.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).isEmpty)) {
                        return 'At least one option is required';
                      }
                      return null;
                    },
                  ),
                  const SizedBox(height: 8),
                  TextFormField(
                    controller: _defaultController,
                    decoration: const InputDecoration(labelText: 'Default value (optional)'),
                  ),
                ],
                if (_dataType == ColumnType.number || _dataType == ColumnType.percent) ...[
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      Expanded(
                        child: TextFormField(
                          controller: _minController,
                          decoration: const InputDecoration(labelText: 'Min (optional)'),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: TextFormField(
                          controller: _maxController,
                          decoration: const InputDecoration(labelText: 'Max (optional)'),
                        ),
                      ),
                    ],
                  ),
                ],
                if (_dataType == ColumnType.currency) ...[
                  const SizedBox(height: 8),
                  CheckboxListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Allow negative amounts'),
                    value: _allowNegative,
                    onChanged: (next) => setState(() => _allowNegative = next ?? false),
                  ),
                ],
                if (_dataType == ColumnType.recordRef) ...[
                  const SizedBox(height: 8),
                  ref
                      .watch(pagesProvider)
                      .maybeWhen(
                        data: (pages) => DropdownButtonFormField<String>(
                          initialValue: _targetPageKey,
                          decoration: const InputDecoration(labelText: 'Links to page'),
                          items: [
                            for (final page in pages)
                              DropdownMenuItem(value: page.key, child: Text(page.name)),
                          ],
                          onChanged: (next) => setState(() => _targetPageKey = next),
                        ),
                        orElse: () => const LinearProgressIndicator(),
                      ),
                  const SizedBox(height: 8),
                  TextFormField(
                    initialValue: _displayColumn,
                    decoration: const InputDecoration(
                      labelText: 'Column to show in the picker',
                      helperText: 'The column key on the linked page, e.g. "name"',
                    ),
                    onChanged: (next) => _displayColumn = next.trim().isEmpty ? null : next.trim(),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('Cancel')),
        FilledButton(onPressed: _save, child: const Text('Save')),
      ],
    );
  }

  void _save() {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    final draft = ColumnDraft(
      name: _nameController.text.trim(),
      dataType: _dataType,
      isRequired: _isRequired,
      isIndexed: _isIndexed,
      isProtected: _isProtected,
      options: _optionsController.text
          .split(',')
          .map((s) => s.trim())
          .where((s) => s.isNotEmpty)
          .toList(),
      defaultValue: _defaultController.text.trim().isEmpty ? null : _defaultController.text.trim(),
      min: _minController.text.trim().isEmpty ? null : _minController.text.trim(),
      max: _maxController.text.trim().isEmpty ? null : _maxController.text.trim(),
      allowNegative: _allowNegative,
      targetPageKey: _targetPageKey,
      displayColumn: _displayColumn,
    );
    Navigator.of(context).pop(draft);
  }
}
