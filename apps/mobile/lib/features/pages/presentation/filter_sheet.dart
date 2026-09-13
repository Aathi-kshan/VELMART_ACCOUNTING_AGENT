import 'package:flutter/material.dart';

import '../domain/column.dart';
import '../domain/page.dart';
import '../domain/record.dart';

/// What the sheet hands back — the caller feeds this straight into
/// `RecordListController.applyQuery` (plan section 3.15, 10.4).
class FilterSheetResult {
  const FilterSheetResult({required this.filters, required this.sort, this.search});

  final List<RecordFilter> filters;
  final List<SortSpec> sort;
  final String? search;
}

/// Filter rows (column → operator → value, restricted to the operators
/// `FilterOp.forType` allows for that column), one sort column + direction,
/// and free-text search — all 10 operators from plan section 10.4.
///
/// Sort is limited to a single column here: every documented example sorts
/// on one column, and the server accepts a list mainly to let a stable id
/// tiebreaker ride along automatically — a multi-sort *builder* UI would be
/// solving a problem nobody using this app actually has.
Future<FilterSheetResult?> showFilterSheet(
  BuildContext context, {
  required PageSchema schema,
  List<RecordFilter> initialFilters = const [],
  SortSpec? initialSort,
  String? initialSearch,
}) {
  return showModalBottomSheet<FilterSheetResult>(
    context: context,
    isScrollControlled: true,
    builder: (context) => _FilterSheet(
      schema: schema,
      initialFilters: initialFilters,
      initialSort: initialSort,
      initialSearch: initialSearch,
    ),
  );
}

class _FilterRow {
  _FilterRow({required this.column, required this.op, this.value});

  PageColumn column;
  FilterOp op;
  Object? value;
}

class _FilterSheet extends StatefulWidget {
  const _FilterSheet({
    required this.schema,
    required this.initialFilters,
    required this.initialSort,
    required this.initialSearch,
  });

  final PageSchema schema;
  final List<RecordFilter> initialFilters;
  final SortSpec? initialSort;
  final String? initialSearch;

  @override
  State<_FilterSheet> createState() => _FilterSheetState();
}

class _FilterSheetState extends State<_FilterSheet> {
  late final List<PageColumn> _filterableColumns = widget.schema.columns
      .where((c) => FilterOp.forType(c.dataType).isNotEmpty)
      .toList();

  late final List<_FilterRow> _rows = _filterableColumns.isEmpty
      ? []
      : widget.initialFilters
            .map((f) {
              final column = widget.schema.columnByKey(f.column);
              return column == null ? null : _FilterRow(column: column, op: f.op, value: f.value);
            })
            .whereType<_FilterRow>()
            .toList();

  late String? _sortColumnKey = widget.initialSort?.column;
  late bool _sortDescending = widget.initialSort?.descending ?? false;
  late final _searchController = TextEditingController(text: widget.initialSearch ?? '');

  void _addRow() {
    if (_filterableColumns.isEmpty) return;
    setState(() {
      final column = _filterableColumns.first;
      _rows.add(_FilterRow(column: column, op: FilterOp.forType(column.dataType).first));
    });
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.75,
      minChildSize: 0.4,
      maxChildSize: 0.95,
      expand: false,
      builder: (context, scrollController) {
        return Padding(
          padding: EdgeInsets.only(
            left: 16,
            right: 16,
            top: 16,
            bottom: MediaQuery.viewInsetsOf(context).bottom + 16,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                children: [
                  Text('Filter & sort', style: Theme.of(context).textTheme.titleLarge),
                  const Spacer(),
                  TextButton(
                    onPressed: () => setState(() {
                      _rows.clear();
                      _sortColumnKey = null;
                      _searchController.clear();
                    }),
                    child: const Text('Clear all'),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView(
                  controller: scrollController,
                  children: [
                    TextField(
                      controller: _searchController,
                      decoration: const InputDecoration(
                        labelText: 'Search',
                        prefixIcon: Icon(Icons.search),
                        border: OutlineInputBorder(),
                      ),
                    ),
                    const SizedBox(height: 16),
                    if (_filterableColumns.isNotEmpty) ...[
                      Text('Sort by', style: Theme.of(context).textTheme.labelLarge),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<String?>(
                              initialValue: _sortColumnKey,
                              decoration: const InputDecoration(border: OutlineInputBorder()),
                              items: [
                                const DropdownMenuItem(value: null, child: Text('Default order')),
                                for (final column in widget.schema.columns)
                                  DropdownMenuItem(value: column.key, child: Text(column.name)),
                              ],
                              onChanged: (next) => setState(() => _sortColumnKey = next),
                            ),
                          ),
                          const SizedBox(width: 8),
                          IconButton(
                            tooltip: _sortDescending ? 'Descending' : 'Ascending',
                            icon: Icon(
                              _sortDescending ? Icons.arrow_downward : Icons.arrow_upward,
                            ),
                            onPressed: _sortColumnKey == null
                                ? null
                                : () => setState(() => _sortDescending = !_sortDescending),
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      Row(
                        children: [
                          Text('Filters', style: Theme.of(context).textTheme.labelLarge),
                          const Spacer(),
                          TextButton.icon(
                            onPressed: _addRow,
                            icon: const Icon(Icons.add),
                            label: const Text('Add filter'),
                          ),
                        ],
                      ),
                      for (var i = 0; i < _rows.length; i++)
                        _FilterRowEditor(
                          key: ValueKey(i),
                          row: _rows[i],
                          columns: _filterableColumns,
                          onChanged: (next) => setState(() => _rows[i] = next),
                          onRemove: () => setState(() => _rows.removeAt(i)),
                        ),
                    ],
                  ],
                ),
              ),
              const SizedBox(height: 8),
              FilledButton(
                onPressed: () {
                  final filters = _rows
                      .map(
                        (row) => RecordFilter(column: row.column.key, op: row.op, value: row.value),
                      )
                      .toList();
                  final sort = _sortColumnKey == null
                      ? <SortSpec>[]
                      : [SortSpec(column: _sortColumnKey!, descending: _sortDescending)];
                  Navigator.of(context).pop(
                    FilterSheetResult(
                      filters: filters,
                      sort: sort,
                      search: _searchController.text.trim(),
                    ),
                  );
                },
                child: const Text('Apply'),
              ),
            ],
          ),
        );
      },
    );
  }
}

class _FilterRowEditor extends StatelessWidget {
  const _FilterRowEditor({
    super.key,
    required this.row,
    required this.columns,
    required this.onChanged,
    required this.onRemove,
  });

  final _FilterRow row;
  final List<PageColumn> columns;
  final ValueChanged<_FilterRow> onChanged;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    final ops = FilterOp.forType(row.column.dataType);

    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<PageColumn>(
                    initialValue: row.column,
                    decoration: const InputDecoration(labelText: 'Column'),
                    items: [
                      for (final column in columns)
                        DropdownMenuItem(value: column, child: Text(column.name)),
                    ],
                    onChanged: (column) {
                      if (column == null) return;
                      onChanged(
                        _FilterRow(column: column, op: FilterOp.forType(column.dataType).first),
                      );
                    },
                  ),
                ),
                IconButton(icon: const Icon(Icons.close), onPressed: onRemove),
              ],
            ),
            DropdownButtonFormField<FilterOp>(
              initialValue: ops.contains(row.op) ? row.op : ops.first,
              decoration: const InputDecoration(labelText: 'Condition'),
              items: [for (final op in ops) DropdownMenuItem(value: op, child: Text(op.label))],
              onChanged: (op) {
                if (op == null) return;
                onChanged(_FilterRow(column: row.column, op: op, value: null));
              },
            ),
            if (row.op != FilterOp.isNull) ...[
              const SizedBox(height: 8),
              _ValueEditor(
                column: row.column,
                op: row.op,
                value: row.value,
                onChanged: (value) =>
                    onChanged(_FilterRow(column: row.column, op: row.op, value: value)),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// A plain value editor for a filter row — deliberately not `FieldRenderer`,
/// which is built for *writing a record* (required-ness, protected locks,
/// reference pickers). A filter value is just a comparison operand.
class _ValueEditor extends StatelessWidget {
  const _ValueEditor({
    required this.column,
    required this.op,
    required this.value,
    required this.onChanged,
  });

  final PageColumn column;
  final FilterOp op;
  final Object? value;
  final ValueChanged<Object?> onChanged;

  @override
  Widget build(BuildContext context) {
    if (op == FilterOp.between) {
      final range = (value is List ? (value as List).cast<Object?>() : const [null, null]);
      return Row(
        children: [
          Expanded(
            child: TextFormField(
              initialValue: range.isNotEmpty ? range[0]?.toString() : null,
              decoration: const InputDecoration(labelText: 'From'),
              onChanged: (input) => onChanged([input, range.length > 1 ? range[1] : null]),
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: TextFormField(
              initialValue: range.length > 1 ? range[1]?.toString() : null,
              decoration: const InputDecoration(labelText: 'To'),
              onChanged: (input) => onChanged([range.isNotEmpty ? range[0] : null, input]),
            ),
          ),
        ],
      );
    }

    if (op == FilterOp.inList) {
      final current = (value is List ? (value as List).cast<String>() : const <String>[]);
      return TextFormField(
        initialValue: current.join(', '),
        decoration: const InputDecoration(labelText: 'Values (comma separated)'),
        onChanged: (input) => onChanged(
          input.split(',').map((s) => s.trim()).where((s) => s.isNotEmpty).toList(),
        ),
      );
    }

    if (column.dataType == ColumnType.boolean) {
      return DropdownButtonFormField<bool>(
        initialValue: value is bool ? value as bool : null,
        decoration: const InputDecoration(labelText: 'Value'),
        items: const [
          DropdownMenuItem(value: true, child: Text('Yes')),
          DropdownMenuItem(value: false, child: Text('No')),
        ],
        onChanged: onChanged,
      );
    }

    if (column.dataType == ColumnType.select || column.dataType == ColumnType.multiSelect) {
      return DropdownButtonFormField<String>(
        initialValue: value is String ? value as String : null,
        decoration: const InputDecoration(labelText: 'Value'),
        items: [
          for (final option in column.options) DropdownMenuItem(value: option, child: Text(option)),
        ],
        onChanged: onChanged,
      );
    }

    return TextFormField(
      initialValue: value?.toString(),
      decoration: const InputDecoration(labelText: 'Value'),
      onChanged: onChanged,
    );
  }
}
