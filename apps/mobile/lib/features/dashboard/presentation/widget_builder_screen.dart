import 'package:flutter/material.dart' hide Page;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/network/api_exception.dart';
import '../../pages/application/pages_providers.dart';
import '../../pages/domain/column.dart';
import '../../pages/domain/page.dart';
import '../application/dashboard_providers.dart';
import '../domain/widget.dart';

/// The Owner builds a widget: pick a page, pick a column + aggregation, add
/// a period, pick a widget type (plan section 15.1's own flow diagram).
///
/// A `WidgetSuggestion` (from `home_screen.dart`'s "accept" flow) pre-fills
/// this form rather than skipping it — the Owner always sees and can edit
/// what they're about to add, never a silent accept.
///
/// `LIST`'s filters aren't editable here yet (out of scope for this pass,
/// matching this project's general bias toward a minimal V1 surface — see
/// `validation_editor_screen.dart`'s own "no live preview" note for the same
/// reasoning) — a `LIST` widget starts unfiltered and can be refined by
/// editing its `config` directly through a future pass.
class WidgetBuilderScreen extends ConsumerStatefulWidget {
  const WidgetBuilderScreen({super.key, this.suggestion});

  final WidgetSuggestion? suggestion;

  @override
  ConsumerState<WidgetBuilderScreen> createState() => _WidgetBuilderScreenState();
}

const _metrics = ['sum', 'avg', 'min', 'max', 'count'];
const _periods = ['all_time', 'current_month', 'last_month', 'current_year'];
const _periodLabels = {
  'all_time': 'All time',
  'current_month': 'Current month',
  'last_month': 'Last month',
  'current_year': 'Current year',
};

class _WidgetBuilderScreenState extends ConsumerState<WidgetBuilderScreen> {
  final _formKey = GlobalKey<FormState>();
  late final _titleController = TextEditingController(text: widget.suggestion?.title ?? '');
  WidgetType _widgetType = WidgetType.metric;
  String? _pageKey;
  String? _column;
  String? _groupBy;
  String _metric = 'sum';
  String _period = 'all_time';
  String _bucket = 'day';
  int _days = 30;
  int _topN = 5;
  String? _visibleTo;
  bool _isSaving = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    final suggestion = widget.suggestion;
    if (suggestion != null) {
      _widgetType = suggestion.widgetType;
      _pageKey = suggestion.pageKey;
      _column = suggestion.config['column'] as String?;
      _groupBy = suggestion.config['group_by'] as String?;
      _metric = suggestion.config['metric'] as String? ?? 'sum';
      _period = suggestion.config['period'] as String? ?? 'all_time';
      _bucket = suggestion.config['bucket'] as String? ?? 'day';
      _days = suggestion.config['days'] as int? ?? 30;
      _topN = suggestion.config['top_n'] as int? ?? 5;
    }
  }

  @override
  void dispose() {
    _titleController.dispose();
    super.dispose();
  }

  Map<String, dynamic> get _config => switch (_widgetType) {
    WidgetType.metric => {'metric': _metric, if (_column != null) 'column': _column, 'period': _period},
    WidgetType.trend => {if (_column != null) 'column': _column, 'metric': _metric, 'bucket': _bucket, 'days': _days},
    WidgetType.breakdown => {
      if (_groupBy != null) 'group_by': _groupBy,
      'metric': _metric,
      if (_column != null) 'column': _column,
      'period': _period,
      'top_n': _topN,
    },
    WidgetType.list => const {},
    WidgetType.reviewQueue => const {},
  };

  Future<void> _save() async {
    if (!(_formKey.currentState?.validate() ?? false) || _pageKey == null) return;
    setState(() {
      _isSaving = true;
      _error = null;
    });
    try {
      await ref
          .read(dashboardRepositoryProvider)
          .createWidget(
            title: _titleController.text.trim(),
            widgetType: _widgetType,
            pageKey: _pageKey!,
            config: _config,
            visibleTo: _visibleTo,
          );
      ref.invalidate(dashboardWidgetsProvider);
      ref.invalidate(widgetSuggestionsProvider);
      if (mounted) context.pop();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isSaving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pagesAsync = ref.watch(pagesProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Add widget')),
      body: pagesAsync.when(
        data: (pages) => _build(context, pages),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load pages.\n$error')),
      ),
    );
  }

  Widget _build(BuildContext context, List<Page> pages) {
    String? selectedPageId;
    for (final candidate in pages) {
      if (candidate.key == _pageKey) {
        selectedPageId = candidate.id;
        break;
      }
    }
    final schemaAsync = selectedPageId == null
        ? null
        : ref.watch(pageSchemaProvider(selectedPageId));

    final needsColumn = _widgetType != WidgetType.list && _widgetType != WidgetType.reviewQueue;
    final needsMetric = needsColumn;
    final needsPeriod = _widgetType == WidgetType.metric || _widgetType == WidgetType.breakdown;
    final needsGroupBy = _widgetType == WidgetType.breakdown;
    final needsTrendFields = _widgetType == WidgetType.trend;
    final needsTopN = _widgetType == WidgetType.breakdown;

    return Form(
      key: _formKey,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          TextFormField(
            controller: _titleController,
            decoration: const InputDecoration(labelText: 'Title'),
            validator: (v) => (v == null || v.trim().isEmpty) ? 'Required' : null,
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<WidgetType>(
            initialValue: _widgetType,
            decoration: const InputDecoration(labelText: 'Widget type'),
            items: [
              for (final type in WidgetType.values)
                DropdownMenuItem(value: type, child: Text(type.label)),
            ],
            onChanged: (next) => setState(() => _widgetType = next ?? _widgetType),
          ),
          const SizedBox(height: 12),
          DropdownButtonFormField<String>(
            initialValue: _pageKey,
            decoration: const InputDecoration(labelText: 'Page'),
            items: [for (final page in pages) DropdownMenuItem(value: page.key, child: Text(page.name))],
            onChanged: (next) => setState(() {
              _pageKey = next;
              _column = null;
              _groupBy = null;
            }),
            validator: (v) => v == null ? 'Required' : null,
          ),
          if (schemaAsync != null) ...[
            const SizedBox(height: 12),
            schemaAsync.when(
              data: (schema) => Column(
                children: [
                  if (needsColumn)
                    DropdownButtonFormField<String>(
                      initialValue: _column,
                      decoration: const InputDecoration(labelText: 'Column'),
                      items: [
                        for (final c in schema.columns.where(_isNumeric))
                          DropdownMenuItem(value: c.key, child: Text(c.name)),
                      ],
                      onChanged: (next) => setState(() => _column = next),
                    ),
                  if (needsGroupBy) ...[
                    const SizedBox(height: 12),
                    DropdownButtonFormField<String>(
                      initialValue: _groupBy,
                      decoration: const InputDecoration(labelText: 'Group by'),
                      items: [
                        for (final c in schema.columns)
                          DropdownMenuItem(value: c.key, child: Text(c.name)),
                      ],
                      onChanged: (next) => setState(() => _groupBy = next),
                    ),
                  ],
                ],
              ),
              loading: () => const LinearProgressIndicator(),
              error: (error, _) => Text('Could not load columns.\n$error'),
            ),
          ],
          if (needsMetric) ...[
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _metric,
              decoration: const InputDecoration(labelText: 'Aggregation'),
              items: [for (final m in _metrics) DropdownMenuItem(value: m, child: Text(m))],
              onChanged: (next) => setState(() => _metric = next ?? _metric),
            ),
          ],
          if (needsPeriod) ...[
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              initialValue: _period,
              decoration: const InputDecoration(labelText: 'Period'),
              items: [
                for (final p in _periods) DropdownMenuItem(value: p, child: Text(_periodLabels[p]!)),
              ],
              onChanged: (next) => setState(() => _period = next ?? _period),
            ),
          ],
          if (needsTrendFields) ...[
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: DropdownButtonFormField<String>(
                    initialValue: _bucket,
                    decoration: const InputDecoration(labelText: 'Bucket'),
                    items: const [
                      DropdownMenuItem(value: 'day', child: Text('Day')),
                      DropdownMenuItem(value: 'week', child: Text('Week')),
                    ],
                    onChanged: (next) => setState(() => _bucket = next ?? _bucket),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: TextFormField(
                    initialValue: '$_days',
                    decoration: const InputDecoration(labelText: 'Days'),
                    keyboardType: TextInputType.number,
                    onChanged: (v) => _days = int.tryParse(v) ?? _days,
                  ),
                ),
              ],
            ),
          ],
          if (needsTopN) ...[
            const SizedBox(height: 12),
            TextFormField(
              initialValue: '$_topN',
              decoration: const InputDecoration(labelText: 'Top N'),
              keyboardType: TextInputType.number,
              onChanged: (v) => _topN = int.tryParse(v) ?? _topN,
            ),
          ],
          const SizedBox(height: 12),
          DropdownButtonFormField<String?>(
            initialValue: _visibleTo,
            decoration: const InputDecoration(labelText: 'Visible to'),
            items: const [
              DropdownMenuItem(value: null, child: Text('Everyone')),
              DropdownMenuItem(value: 'OWNER', child: Text('Owner only')),
              DropdownMenuItem(value: 'MANAGER', child: Text('Manager only')),
            ],
            onChanged: (next) => setState(() => _visibleTo = next),
          ),
          const SizedBox(height: 24),
          FilledButton(
            onPressed: _isSaving ? null : _save,
            child: _isSaving
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Text('Add widget'),
          ),
        ],
      ),
    );
  }
}

bool _isNumeric(PageColumn column) => switch (column.dataType) {
  ColumnType.number || ColumnType.currency || ColumnType.percent => true,
  _ => false,
};
