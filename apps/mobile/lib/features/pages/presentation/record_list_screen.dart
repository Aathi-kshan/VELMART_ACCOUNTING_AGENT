import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/widgets/adaptive_scaffold.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/empty_state.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../application/record_list_controller.dart';
import '../domain/column.dart';
import '../domain/page.dart';
import '../domain/record.dart';
import 'filter_sheet.dart';
import 'record_detail_screen.dart';

/// Records for one page (plan section 3.14) — a dense grid on desktop, a
/// card list on mobile, master-detail in between, all driven by the same
/// schema (plan section 10.4). Layout choice mirrors `AdaptiveScaffold`'s own
/// breakpoints (plan section 22.4) but is decided here, independently: this
/// screen is pushed on top of the shell (a drill-in), not one of its tabs.
class RecordListScreen extends ConsumerStatefulWidget {
  const RecordListScreen({super.key, required this.pageId});

  final String pageId;

  @override
  ConsumerState<RecordListScreen> createState() => _RecordListScreenState();
}

class _RecordListScreenState extends ConsumerState<RecordListScreen> {
  String? _selectedRecordId;
  bool _isExporting = false;

  Future<void> _openFilters(PageSchema schema, RecordListState state) async {
    final result = await showFilterSheet(
      context,
      schema: schema,
      initialFilters: state.query.filters,
      initialSort: state.query.sort.isEmpty ? null : state.query.sort.first,
      initialSearch: state.query.search,
    );
    if (result == null) return;
    await ref
        .read(recordListControllerProvider(widget.pageId).notifier)
        .applyQuery(filters: result.filters, sort: result.sort, search: result.search);
  }

  /// Exports whatever filter/search this list currently has applied —
  /// "export what I'm looking at" (plan section 13.2, P3.5 Part 2) — then
  /// hands the bytes straight to the OS share sheet. Owner-only on the
  /// server; `canExportCsv` just keeps the button off a manager's screen.
  Future<void> _exportCsv(PageSchema schema, RecordListState state) async {
    if (_isExporting) return;
    setState(() => _isExporting = true);
    try {
      final bytes = await ref
          .read(pageRepositoryProvider)
          .exportCsv(schema.page.id, filters: state.query.filters, search: state.query.search);
      await Share.shareXFiles([
        XFile.fromData(bytes, name: '${schema.page.key}.csv', mimeType: 'text/csv'),
      ]);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(e.detail)));
    } finally {
      if (mounted) setState(() => _isExporting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final schemaAsync = ref.watch(pageSchemaProvider(widget.pageId));

    return schemaAsync.when(
      data: (schema) => _build(context, schema),
      loading: () => Scaffold(
        appBar: AppBar(),
        body: const Center(child: CircularProgressIndicator()),
      ),
      error: (error, _) => Scaffold(
        appBar: AppBar(),
        body: Center(child: Text('Could not load this page.\n$error')),
      ),
    );
  }

  Widget _build(BuildContext context, PageSchema schema) {
    final listState = ref.watch(recordListControllerProvider(widget.pageId));
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated ? authState.user.role : UserRole.manager;

    return Scaffold(
      appBar: AppBar(
        title: Text(schema.page.name),
        actions: [
          if (canExportCsv(role))
            IconButton(
              icon: _isExporting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.file_download_outlined),
              tooltip: 'Export CSV',
              onPressed: _isExporting ? null : () => _exportCsv(schema, listState),
            ),
          IconButton(
            icon: Badge(
              isLabelVisible: listState.query.filters.isNotEmpty,
              child: const Icon(Icons.filter_list),
            ),
            tooltip: 'Filter & sort',
            onPressed: () => _openFilters(schema, listState),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.pushNamed('recordNew', pathParameters: {'pageId': schema.page.id}),
        tooltip: 'New record',
        child: const Icon(Icons.add),
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth;
          if (width >= AdaptiveScaffold.sidebarBreakpoint) {
            return _DenseGrid(schema: schema, state: listState, role: role);
          }
          if (width >= AdaptiveScaffold.railBreakpoint) {
            return _MasterDetail(
              schema: schema,
              state: listState,
              selectedRecordId: _selectedRecordId,
              onSelect: (id) => setState(() => _selectedRecordId = id),
            );
          }
          return _CardList(schema: schema, state: listState);
        },
      ),
    );
  }
}

/// Loads more when the scroll position nears the end — shared by the card
/// list and the dense grid.
class _LoadMoreListener extends ConsumerWidget {
  const _LoadMoreListener({
    required this.pageId,
    required this.hasMore,
    required this.child,
  });

  final String pageId;
  final bool hasMore;
  final Widget child;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return NotificationListener<ScrollNotification>(
      onNotification: (notification) {
        if (!hasMore) return false;
        if (notification.metrics.extentAfter < 300) {
          ref.read(recordListControllerProvider(pageId).notifier).loadMore();
        }
        return false;
      },
      child: child,
    );
  }
}

class _CardList extends ConsumerWidget {
  const _CardList({required this.schema, required this.state});

  final PageSchema schema;
  final RecordListState state;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.isLoading && state.items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.items.isEmpty) {
      return const EmptyState(
        icon: Icons.receipt_long_outlined,
        message: 'No records yet. Tap + to add the first one.',
      );
    }

    return _LoadMoreListener(
      pageId: schema.page.id,
      hasMore: state.hasMore,
      child: RefreshIndicator(
        onRefresh: () =>
            ref.read(recordListControllerProvider(schema.page.id).notifier).refresh(),
        child: ListView.separated(
          padding: const EdgeInsets.all(8),
          itemCount: state.items.length + (state.isLoadingMore ? 1 : 0),
          separatorBuilder: (context, index) => const Divider(height: 1),
          itemBuilder: (context, index) {
            if (index >= state.items.length) {
              return const Padding(
                padding: EdgeInsets.all(16),
                child: Center(child: CircularProgressIndicator()),
              );
            }
            final record = state.items[index];
            return _RecordCard(schema: schema, record: record);
          },
        ),
      ),
    );
  }
}

class _RecordCard extends StatelessWidget {
  const _RecordCard({required this.schema, required this.record});

  final PageSchema schema;
  final PageRecord record;

  @override
  Widget build(BuildContext context) {
    final displayColumn = schema.displayColumn;
    final title = displayColumn == null
        ? record.id
        : (record.valueFor(displayColumn)?.toString() ?? '(blank)');
    PageColumn? currencyColumn;
    for (final column in schema.columns) {
      if (column.dataType == ColumnType.currency) {
        currencyColumn = column;
        break;
      }
    }

    return ListTile(
      title: Text(title),
      subtitle: Text(formatDate(record.businessDate)),
      trailing: currencyColumn == null
          ? (record.needsReview ? const Icon(Icons.flag_outlined) : null)
          : AmountText(record.valueFor(currencyColumn)),
      onTap: () => context.pushNamed('recordDetail', pathParameters: {'recordId': record.id}),
    );
  }
}

class _MasterDetail extends StatelessWidget {
  const _MasterDetail({
    required this.schema,
    required this.state,
    required this.selectedRecordId,
    required this.onSelect,
  });

  final PageSchema schema;
  final RecordListState state;
  final String? selectedRecordId;
  final ValueChanged<String?> onSelect;

  @override
  Widget build(BuildContext context) {
    PageRecord? selected;
    for (final record in state.items) {
      if (record.id == selectedRecordId) {
        selected = record;
        break;
      }
    }

    return Row(
      children: [
        SizedBox(
          width: 320,
          child: state.items.isEmpty && !state.isLoading
              ? const EmptyState(message: 'No records yet.')
              : _LoadMoreListener(
                  pageId: schema.page.id,
                  hasMore: state.hasMore,
                  child: ListView.builder(
                    itemCount: state.items.length,
                    itemBuilder: (context, index) {
                      final record = state.items[index];
                      final displayColumn = schema.displayColumn;
                      final title = displayColumn == null
                          ? record.id
                          : (record.valueFor(displayColumn)?.toString() ?? '(blank)');
                      return ListTile(
                        title: Text(title),
                        subtitle: Text(formatDate(record.businessDate)),
                        selected: record.id == selectedRecordId,
                        onTap: () => onSelect(record.id),
                      );
                    },
                  ),
                ),
        ),
        const VerticalDivider(width: 1),
        Expanded(
          child: selected == null
              ? const EmptyState(message: 'Select a record to view it here.')
              : RecordDetailView(
                  key: ValueKey(selected.id),
                  record: selected,
                  schema: schema,
                  onEdit: () => context.pushNamed(
                    'recordEdit',
                    pathParameters: {'recordId': selected!.id},
                  ),
                  onDeleted: () => onSelect(null),
                ),
        ),
      ],
    );
  }
}

class _DenseGrid extends StatelessWidget {
  const _DenseGrid({required this.schema, required this.state, required this.role});

  final PageSchema schema;
  final RecordListState state;
  final UserRole role;

  @override
  Widget build(BuildContext context) {
    if (state.isLoading && state.items.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (state.items.isEmpty) {
      return const EmptyState(message: 'No records yet.');
    }

    return _LoadMoreListener(
      pageId: schema.page.id,
      hasMore: state.hasMore,
      child: SingleChildScrollView(
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: DataTable(
            columnSpacing: 24,
            columns: [
              const DataColumn(label: Text('Date')),
              for (final column in schema.columns) DataColumn(label: Text(column.name)),
            ],
            rows: [
              for (final record in state.items)
                DataRow(
                  onSelectChanged: (_) => context.pushNamed(
                    'recordDetail',
                    pathParameters: {'recordId': record.id},
                  ),
                  cells: [
                    DataCell(Text(formatDate(record.businessDate))),
                    for (final column in schema.columns)
                      DataCell(_CellValue(column: column, record: record)),
                  ],
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CellValue extends StatelessWidget {
  const _CellValue({required this.column, required this.record});

  final PageColumn column;
  final PageRecord record;

  @override
  Widget build(BuildContext context) {
    final value = record.valueFor(column);
    if (column.dataType == ColumnType.currency) return AmountText(value, colorByValue: true);
    if (column.dataType == ColumnType.date) return Text(formatDate(value));
    if (column.dataType == ColumnType.datetime) return Text(formatDateTime(value));
    if (column.dataType == ColumnType.boolean) return Text(value == true ? 'Yes' : 'No');
    if (value is List) return Text(value.join(', '));
    return Text(value?.toString() ?? '');
  }
}
