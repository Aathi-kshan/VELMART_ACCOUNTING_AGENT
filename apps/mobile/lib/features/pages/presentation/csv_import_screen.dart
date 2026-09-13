import 'dart:typed_data';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../application/pages_providers.dart';
import '../domain/column.dart';
import '../domain/csv_import.dart';
import '../domain/page.dart';
import 'import_history_screen.dart';

enum _Stage { pickFile, mapping, validated, committed }

/// The CSV import wizard (plan section 13.1, P3.5 Part 3) — pick a file,
/// review/adjust the server's fuzzy-suggested column mapping, validate
/// every row (money/date normalization, natural-key duplicate detection),
/// then commit. Owner only; the server enforces that regardless of this
/// screen even existing.
class CsvImportScreen extends ConsumerStatefulWidget {
  const CsvImportScreen({super.key, required this.pageId});

  final String pageId;

  @override
  ConsumerState<CsvImportScreen> createState() => _CsvImportScreenState();
}

class _CsvImportScreenState extends ConsumerState<CsvImportScreen> {
  _Stage _stage = _Stage.pickFile;
  bool _isBusy = false;
  String? _error;

  Uint8List? _fileBytes;
  String _fileName = 'import.csv';
  ImportPreview? _preview;

  final Map<String, String?> _mapping = {};
  final Set<String> _naturalKeyColumns = {};
  DuplicateStrategy _duplicateStrategy = DuplicateStrategy.createAnyway;
  final Map<String, DateFormatHint?> _dateFormats = {};

  ImportValidation? _validation;
  ImportCommitResult? _commitResult;

  ImportMapping _buildMapping() {
    final mapping = <String, String>{
      for (final entry in _mapping.entries)
        if (entry.value != null) entry.key: entry.value!,
    };
    final dateFormats = <String, DateFormatHint>{
      for (final entry in _dateFormats.entries)
        if (entry.value != null) entry.key: entry.value!,
    };
    return ImportMapping(
      mapping: mapping,
      naturalKeyColumns: _naturalKeyColumns.toList(),
      duplicateStrategy: _duplicateStrategy,
      dateFormats: dateFormats,
    );
  }

  Future<void> _pickFile() async {
    final result = await FilePicker.platform.pickFiles(
      type: FileType.custom,
      allowedExtensions: ['csv'],
      withData: true,
    );
    final files = result?.files;
    final file = (files != null && files.isNotEmpty) ? files.first : null;
    if (file?.bytes == null) return;

    setState(() {
      _fileBytes = file!.bytes;
      _fileName = file.name;
      _isBusy = true;
      _error = null;
    });

    try {
      final preview = await ref
          .read(pageRepositoryProvider)
          .previewImport(widget.pageId, bytes: _fileBytes!, fileName: _fileName);
      setState(() {
        _preview = preview;
        _mapping
          ..clear()
          ..addAll(preview.suggestedMapping);
        _stage = _Stage.mapping;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _validate(PageSchema schema) async {
    setState(() {
      _isBusy = true;
      _error = null;
    });
    try {
      final validation = await ref
          .read(pageRepositoryProvider)
          .validateImport(
            widget.pageId,
            bytes: _fileBytes!,
            fileName: _fileName,
            mapping: _buildMapping(),
          );
      setState(() {
        _validation = validation;
        _stage = _Stage.validated;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  Future<void> _commit() async {
    setState(() {
      _isBusy = true;
      _error = null;
    });
    try {
      final result = await ref
          .read(pageRepositoryProvider)
          .commitImport(
            widget.pageId,
            bytes: _fileBytes!,
            fileName: _fileName,
            mapping: _buildMapping(),
          );
      ref.invalidate(importBatchesProvider(widget.pageId));
      setState(() {
        _commitResult = result;
        _stage = _Stage.committed;
      });
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isBusy = false);
    }
  }

  void _reset() {
    setState(() {
      _stage = _Stage.pickFile;
      _fileBytes = null;
      _preview = null;
      _mapping.clear();
      _naturalKeyColumns.clear();
      _duplicateStrategy = DuplicateStrategy.createAnyway;
      _dateFormats.clear();
      _validation = null;
      _commitResult = null;
      _error = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final schemaAsync = ref.watch(pageSchemaProvider(widget.pageId));

    return Scaffold(
      appBar: AppBar(
        title: const Text('Import CSV'),
        actions: [
          IconButton(
            icon: const Icon(Icons.history),
            tooltip: 'Import history',
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => ImportHistoryScreen(pageId: widget.pageId)),
            ),
          ),
        ],
      ),
      body: schemaAsync.when(
        data: (schema) => _body(schema),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load this page.\n$error')),
      ),
    );
  }

  Widget _body(PageSchema schema) {
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_error != null) ...[
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(_error!),
            ),
          ),
          const SizedBox(height: 16),
        ],
        switch (_stage) {
          _Stage.pickFile => _pickFileStep(),
          _Stage.mapping => _mappingStep(schema),
          _Stage.validated => _validatedStep(schema),
          _Stage.committed => _committedStep(),
        },
      ],
    );
  }

  Widget _pickFileStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Text('Pick a CSV file (up to 10 MB) to import into this page.'),
        const SizedBox(height: 16),
        FilledButton.icon(
          onPressed: _isBusy ? null : _pickFile,
          icon: _isBusy
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.upload_file),
          label: const Text('Choose file'),
        ),
      ],
    );
  }

  Widget _mappingStep(PageSchema schema) {
    final preview = _preview!;
    final importable = schema.columns
        .where((c) => !c.dataType.isReadOnly && !schema.generatedColumns.contains(c.key))
        .toList();
    final usedKeys = _mapping.values.whereType<String>().toSet();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          '${preview.rowCount} rows detected (${preview.encoding}, delimiter '
          '"${preview.delimiter}")',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
        const SizedBox(height: 16),
        Text('Column mapping', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 8),
        for (final header in preview.headers)
          Padding(
            padding: const EdgeInsets.only(bottom: 8),
            child: Row(
              children: [
                Expanded(child: Text(header)),
                const SizedBox(width: 8),
                Expanded(
                  child: DropdownButtonFormField<String?>(
                    initialValue: _mapping[header],
                    isExpanded: true,
                    decoration: const InputDecoration(isDense: true),
                    items: [
                      const DropdownMenuItem(value: null, child: Text('Don\'t import')),
                      for (final column in importable)
                        DropdownMenuItem(
                          value: column.key,
                          enabled: !usedKeys.contains(column.key) || _mapping[header] == column.key,
                          child: Text(column.name),
                        ),
                    ],
                    onChanged: (value) => setState(() => _mapping[header] = value),
                  ),
                ),
              ],
            ),
          ),
        if (preview.sampleRows.isNotEmpty) ...[
          const SizedBox(height: 8),
          ExpansionTile(
            title: const Text('Preview raw rows'),
            children: [
              for (final row in preview.sampleRows)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                  child: Text(
                    row.values.join(' · '),
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ),
            ],
          ),
        ],
        const SizedBox(height: 24),
        Text('Duplicate handling', style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: 4),
        Text(
          'Pick the mapped column(s) that identify "the same row" — for '
          'example Date + Cheque Number.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        for (final column in importable.where((c) => usedKeys.contains(c.key)))
          CheckboxListTile(
            title: Text(column.name),
            value: _naturalKeyColumns.contains(column.key),
            onChanged: (checked) => setState(() {
              if (checked ?? false) {
                _naturalKeyColumns.add(column.key);
              } else {
                _naturalKeyColumns.remove(column.key);
              }
            }),
            controlAffinity: ListTileControlAffinity.leading,
            dense: true,
          ),
        if (_naturalKeyColumns.isNotEmpty) ...[
          const SizedBox(height: 8),
          for (final strategy in DuplicateStrategy.values)
            RadioListTile<DuplicateStrategy>(
              title: Text(strategy.label),
              value: strategy,
              // ignore: deprecated_member_use
              groupValue: _duplicateStrategy,
              // ignore: deprecated_member_use
              onChanged: (value) => setState(() => _duplicateStrategy = value!),
              dense: true,
            ),
        ],
        const SizedBox(height: 16),
        for (final column in importable)
          if (usedKeys.contains(column.key) &&
              (column.dataType == ColumnType.date || column.dataType == ColumnType.datetime))
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: DropdownButtonFormField<DateFormatHint?>(
                initialValue: _dateFormats[column.key],
                decoration: InputDecoration(
                  labelText: '${column.name}: date format (only if ambiguous, e.g. 01/02/2026)',
                  isDense: true,
                ),
                items: [
                  const DropdownMenuItem(value: null, child: Text('Not set')),
                  for (final hint in DateFormatHint.values)
                    DropdownMenuItem(value: hint, child: Text(hint.label)),
                ],
                onChanged: (value) => setState(() => _dateFormats[column.key] = value),
              ),
            ),
        const SizedBox(height: 16),
        Row(
          children: [
            OutlinedButton(onPressed: _isBusy ? null : _reset, child: const Text('Start over')),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: _isBusy || usedKeys.isEmpty ? null : () => _validate(schema),
              child: _isBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Text('Validate'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _validatedStep(PageSchema schema) {
    final validation = _validation!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${validation.totalRows} rows in file', style: Theme.of(context).textTheme.bodyMedium),
        const SizedBox(height: 8),
        Wrap(
          spacing: 8,
          children: [
            Chip(label: Text('${validation.validRows} valid')),
            if (validation.duplicateRows > 0)
              Chip(label: Text('${validation.duplicateRows} duplicates')),
            if (validation.errorRows > 0)
              Chip(
                label: Text('${validation.errorRows} errors'),
                backgroundColor: Theme.of(context).colorScheme.errorContainer,
              ),
          ],
        ),
        if (validation.errors.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text('Row errors', style: Theme.of(context).textTheme.titleMedium),
          if (validation.errorsTruncated)
            Text(
              'Showing the first ${validation.errors.length} errors.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          for (final error in validation.errors)
            ListTile(
              dense: true,
              leading: const Icon(Icons.error_outline),
              title: Text(
                error.column == null
                    ? 'Row ${error.row}'
                    : 'Row ${error.row} — ${error.column}',
              ),
              subtitle: Text(error.message),
            ),
        ],
        const SizedBox(height: 16),
        Row(
          children: [
            OutlinedButton(
              onPressed: _isBusy ? null : () => setState(() => _stage = _Stage.mapping),
              child: const Text('Back to mapping'),
            ),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: _isBusy || validation.validRows == 0 ? null : _commit,
              child: _isBusy
                  ? const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Text('Import ${validation.validRows} rows'),
            ),
          ],
        ),
      ],
    );
  }

  Widget _committedStep() {
    final result = _commitResult!;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(Icons.check_circle, color: Theme.of(context).colorScheme.primary),
            const SizedBox(width: 8),
            Text('Import complete', style: Theme.of(context).textTheme.titleMedium),
          ],
        ),
        const SizedBox(height: 8),
        Text('${result.importedRows} imported, ${result.skippedRows} skipped'),
        const SizedBox(height: 4),
        Text(
          'Rollback is available for 24 hours from the import history screen.',
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        Row(
          children: [
            OutlinedButton(onPressed: _reset, child: const Text('Import another file')),
            const SizedBox(width: 12),
            FilledButton(
              onPressed: () => context.pop(),
              child: const Text('Done'),
            ),
          ],
        ),
      ],
    );
  }
}
