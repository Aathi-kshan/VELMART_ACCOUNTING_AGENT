import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';
import 'package:share_plus/share_plus.dart';

import '../../../core/date/business_date.dart';
import '../../../core/money/money.dart';
import '../../../core/navigation/active_page.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/permissions/can.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radii.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_typography.dart';
import '../../../core/widgets/adaptive_scaffold.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_filter_bar.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/app_record_card.dart';
import '../../../core/widgets/app_status_chip.dart';
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

/// Records for one page — a card list below 600dp, a dense table from
/// 600dp up. Nested inside the shell so the 5-slot bar stays visible;
/// Add record is the shell's center **+** on compact widths and a header
/// button on the table layout.
class RecordListScreen extends ConsumerStatefulWidget {
  const RecordListScreen({super.key, required this.pageId});

  final String pageId;

  @override
  ConsumerState<RecordListScreen> createState() => _RecordListScreenState();
}

class _RecordListScreenState extends ConsumerState<RecordListScreen> {
  bool _isExporting = false;
  final _search = TextEditingController();

  @override
  void dispose() {
    _search.dispose();
    super.dispose();
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ref.read(activePageProvider.notifier).state = ActivePage(
        id: widget.pageId,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    ref.listen(pageSchemaProvider(widget.pageId), (previous, next) {
      next.whenData((schema) {
        Future.microtask(() {
          if (!mounted) return;
          ref.read(activePageProvider.notifier).state = ActivePage(
            id: schema.page.id,
            name: schema.page.name,
          );
        });
      });
    });

    final schemaAsync = ref.watch(pageSchemaProvider(widget.pageId));

    return schemaAsync.when(
      data: (schema) => _build(context, schema),
      loading: () => const Scaffold(body: AppLoadingState()),
      error: (error, _) => Scaffold(
        appBar: AppBar(),
        body: AppErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(pageSchemaProvider(widget.pageId)),
        ),
      ),
    );
  }

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
        .applyQuery(
          filters: result.filters,
          sort: result.sort,
          search: result.search,
        );
    ref.invalidate(recordSummaryProvider(widget.pageId));
  }

  Future<void> _exportCsv(PageSchema schema, RecordListState state) async {
    if (_isExporting) return;
    setState(() => _isExporting = true);
    try {
      final bytes = await ref
          .read(pageRepositoryProvider)
          .exportCsv(
            schema.page.id,
            filters: state.query.filters,
            search: state.query.search,
          );
      await Share.shareXFiles([
        XFile.fromData(
          bytes,
          name: '${schema.page.key}.csv',
          mimeType: 'text/csv',
        ),
      ]);
    } on ApiException catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(e.detail)));
    } finally {
      if (mounted) setState(() => _isExporting = false);
    }
  }

  /// The count half of the strip — design.md §16.5: `"128 records"`, never
  /// a fabricated total.
  String? _countLabel(RecordSummary? summary) {
    if (summary == null) return null;
    final count = NumberFormat('#,###').format(summary.recordCount);
    return '$count record${summary.recordCount == 1 ? '' : 's'}';
  }

  /// The desktop header's subtitle keeps the date-range framing the
  /// original mockup shows there ("128 records · 1–13 September") — the
  /// compact summary strip below shows the sum instead, since that's the
  /// half of `RecordSummary` a plain subtitle line has no room for.
  String? _summaryLine(RecordSummary? summary) {
    final countLabel = _countLabel(summary);
    if (countLabel == null) return null;
    final now = DateTime.now();
    final months = [
      'January',
      'February',
      'March',
      'April',
      'May',
      'June',
      'July',
      'August',
      'September',
      'October',
      'November',
      'December',
    ];
    return '$countLabel · 1–${now.day} ${months[now.month - 1]}';
  }

  Future<void> _applySearch(String pageId) async {
    await ref
        .read(recordListControllerProvider(pageId).notifier)
        .applyQuery(
          search: _search.text.trim(),
          clearSearch: _search.text.trim().isEmpty,
        );
    ref.invalidate(recordSummaryProvider(pageId));
  }

  Widget _build(BuildContext context, PageSchema schema) {
    final listState = ref.watch(recordListControllerProvider(widget.pageId));
    final summary = ref.watch(recordSummaryProvider(widget.pageId)).valueOrNull;
    final authState = ref.watch(authControllerProvider);
    final role = authState is AuthAuthenticated
        ? authState.user.role
        : UserRole.manager;
    final windowWidth = MediaQuery.sizeOf(context).width;
    final showTable = AdaptiveScaffold.isTableLayout(windowWidth);

    final users = role == UserRole.owner
        ? ref.watch(usersProvider).valueOrNull
        : null;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: showTable
          ? null
          : AppBar(
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
                    onPressed: _isExporting
                        ? null
                        : () => _exportCsv(schema, listState),
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
      body: Column(
        children: [
          if (showTable)
            _DesktopRecordsHeader(
              title: schema.page.name,
              subtitle: _summaryLine(summary),
              search: _search,
              filterActive: listState.query.filters.isNotEmpty,
              onSearch: () => _applySearch(schema.page.id),
              onFilter: () => _openFilters(schema, listState),
              onAdd: () => context.pushNamed(
                'recordNew',
                pathParameters: {'pageId': schema.page.id},
              ),
            )
          else if (_countLabel(summary) != null)
            _SummaryStrip(countLabel: _countLabel(summary)!, summary: summary!),
          if (listState.query.filters.isNotEmpty ||
              (listState.query.search != null &&
                  listState.query.search!.isNotEmpty))
            AppFilterBar(
              chips: [
                if (listState.query.search != null &&
                    listState.query.search!.isNotEmpty)
                  Chip(label: Text('Search: ${listState.query.search}')),
                for (final filter in listState.query.filters)
                  Chip(label: Text('${filter.column} ${filter.op.label}')),
              ],
              onClear: () {
                ref
                    .read(recordListControllerProvider(widget.pageId).notifier)
                    .applyQuery(
                      filters: const [],
                      sort: const [],
                      clearSearch: true,
                    );
                ref.invalidate(recordSummaryProvider(widget.pageId));
              },
            ),
          Expanded(
            child: showTable
                ? _DenseGrid(schema: schema, state: listState, users: users)
                : _CardList(schema: schema, state: listState, role: role),
          ),
        ],
      ),
    );
  }
}

/// The compact record list's summary strip (design.md §16.5, §11 mockup
/// layout): count on the left, the page's own aggregate sum on the right
/// — `RecordSummary.sumLabel`/`sumValue` were already fetched for this but
/// previously discarded in favor of a plain unbordered text line.
class _SummaryStrip extends StatelessWidget {
  const _SummaryStrip({required this.countLabel, required this.summary});

  final String countLabel;
  final RecordSummary summary;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return DecoratedBox(
      decoration: const BoxDecoration(
        color: AppColors.surface,
        border: Border.symmetric(
          horizontal: BorderSide(color: AppColors.border),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(countLabel, style: textTheme.labelMedium),
            if (summary.sumLabel != null && summary.sumValue != null)
              Row(
                children: [
                  Text(
                    '${summary.sumLabel}  ',
                    style: textTheme.labelMedium?.copyWith(
                      color: AppColors.textTertiary,
                    ),
                  ),
                  Text(
                    summary.sumValue!,
                    style: AppTypography.dataStrong(
                      color: AppColors.textPrimary,
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}

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
  const _CardList({
    required this.schema,
    required this.state,
    required this.role,
  });

  final PageSchema schema;
  final RecordListState state;
  final UserRole role;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.isLoading && state.items.isEmpty) {
      return const AppLoadingState();
    }
    if (state.error != null && state.items.isEmpty) {
      return AppErrorState(
        message: state.error!.detail,
        onRetry: () => ref
            .read(recordListControllerProvider(schema.page.id).notifier)
            .refresh(),
      );
    }
    if (state.items.isEmpty) {
      final isFiltered =
          state.query.filters.isNotEmpty ||
          (state.query.search?.isNotEmpty ?? false);
      if (isFiltered) {
        return EmptyState.filtered(
          onClear: () => ref
              .read(recordListControllerProvider(schema.page.id).notifier)
              .applyQuery(filters: const [], sort: const [], clearSearch: true),
        );
      }
      final expanded = AdaptiveScaffold.isExpanded(
        MediaQuery.sizeOf(context).width,
      );
      return EmptyState(
        icon: Icons.receipt_long_outlined,
        title: 'No records yet',
        message: expanded
            ? 'Tap Add record to enter the first one.'
            : 'Tap + to enter the first one.',
      );
    }

    return _LoadMoreListener(
      pageId: schema.page.id,
      hasMore: state.hasMore,
      child: RefreshIndicator(
        onRefresh: () => ref
            .read(recordListControllerProvider(schema.page.id).notifier)
            .refresh(),
        child: ListView.separated(
          padding: const EdgeInsets.all(AppSpacing.md),
          itemCount: state.items.length + (state.isLoadingMore ? 1 : 0),
          separatorBuilder: (context, index) =>
              const SizedBox(height: AppSpacing.sm),
          itemBuilder: (context, index) {
            if (index >= state.items.length) {
              return const Padding(
                padding: EdgeInsets.all(AppSpacing.md),
                child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
              );
            }
            final record = state.items[index];
            return _RecordCard(schema: schema, record: record, role: role);
          },
        ),
      ),
    );
  }
}

/// Compact card contents for one record — title, date, primary money, and
/// up to two supporting fields from *this* page's schema (not a hardcoded
/// Expenses layout).
class RecordCardDetails {
  const RecordCardDetails({
    required this.title,
    this.subtitle,
    this.amount,
    this.supporting = const [],
  });

  final String title;
  final String? subtitle;
  final Object? amount;
  final List<String> supporting;
}

PageColumn? cardAmountColumn(PageSchema schema) {
  for (final key in schema.generatedColumns) {
    final column = schema.columnByKey(key);
    if (column != null && column.dataType == ColumnType.currency) return column;
  }
  const preferred = {'total_revenue', 'total_amount', 'paid_amount', 'amount'};
  for (final column in schema.columns) {
    if (column.dataType == ColumnType.currency &&
        preferred.contains(column.key)) {
      return column;
    }
  }
  for (final column in schema.columns) {
    if (column.dataType == ColumnType.currency) return column;
  }
  return null;
}

PageColumn? cardTitleColumn(PageSchema schema) {
  for (final column in schema.columns) {
    if (column.dataType == ColumnType.text) return column;
  }
  for (final column in schema.columns) {
    if (column.dataType == ColumnType.longText) return column;
  }
  return null;
}

RecordCardDetails recordCardDetails(PageSchema schema, PageRecord record) {
  final titleColumn = cardTitleColumn(schema);
  final amountColumn = cardAmountColumn(schema);
  final title = titleColumn == null
      ? formatDate(record.businessDate)
      : formatRecordValue(titleColumn, record.valueFor(titleColumn));
  final extras = <String>[
    for (final column in schema.columns)
      if (column != titleColumn &&
          column != amountColumn &&
          column.dataType != ColumnType.date &&
          column.dataType != ColumnType.datetime &&
          !column.dataType.isReadOnly)
        '${column.name}: ${formatRecordValue(column, record.valueFor(column))}',
  ];
  return RecordCardDetails(
    title: title,
    subtitle: titleColumn == null ? null : formatDate(record.businessDate),
    amount: amountColumn == null ? null : record.valueFor(amountColumn),
    supporting: extras.take(2).toList(),
  );
}

class _RecordCard extends ConsumerWidget {
  const _RecordCard({
    required this.schema,
    required this.record,
    required this.role,
  });

  final PageSchema schema;
  final PageRecord record;
  final UserRole role;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final details = recordCardDetails(schema, record);

    return Stack(
      children: [
        AppRecordCard(
          title: details.title,
          subtitle: details.subtitle,
          amount: details.amount,
          supporting: details.supporting,
          status: record.needsReview
              ? const AppStatusChip(
                  label: 'Needs review',
                  tone: AppStatusTone.warning,
                  icon: Icons.flag_outlined,
                )
              : AppStatusChip.recordStatus(record.status.wire),
          onTap: () => context.pushNamed(
            'recordDetail',
            pathParameters: {'recordId': record.id},
          ),
        ),
        if (canEditRecord(role) || canDeleteRecord(role))
          Positioned(
            right: 4,
            bottom: 4,
            child: PopupMenuButton<String>(
              tooltip: 'Record actions',
              onSelected: (action) {
                switch (action) {
                  case 'edit':
                    context.pushNamed(
                      'recordEdit',
                      pathParameters: {'recordId': record.id},
                    );
                  case 'delete':
                    confirmAndDeleteRecord(context, ref, record);
                }
              },
              itemBuilder: (context) => [
                if (canEditRecord(role))
                  const PopupMenuItem(value: 'edit', child: Text('Edit')),
                if (canDeleteRecord(role))
                  const PopupMenuItem(value: 'delete', child: Text('Delete')),
              ],
            ),
          ),
      ],
    );
  }
}

String formatRecordValue(PageColumn column, Object? value) {
  if (value == null || (value is String && value.isEmpty)) return '—';
  switch (column.dataType) {
    case ColumnType.currency:
      try {
        return Money.parse('$value').format();
      } on FormatException {
        return '$value';
      }
    case ColumnType.date:
      return formatDate(value);
    case ColumnType.datetime:
      return formatDateTime(value);
    case ColumnType.boolean:
      return value == true ? 'Yes' : 'No';
    case ColumnType.select:
      final raw = '$value';
      if (raw == raw.toUpperCase() && raw.length > 1) {
        return '${raw[0]}${raw.substring(1).toLowerCase()}';
      }
      return raw;
    default:
      if (value is List) return value.join(', ');
      return '$value';
  }
}

/// Columns shown in the dense table: schema order, minus the page's own
/// date column (the leading **Date** is `business_date`) and `entry_time`.
List<PageColumn> tableColumnsFor(PageSchema schema) {
  return [
    for (final column in schema.columns)
      if (!_omitFromTable(schema, column)) column,
  ];
}

bool _omitFromTable(PageSchema schema, PageColumn column) {
  if (column.dataType == ColumnType.attachment) return true;
  if (column.key == 'entry_time' && column.dataType == ColumnType.datetime) {
    return true;
  }
  if (column.dataType == ColumnType.date &&
      column.key == schema.page.dateColumnKey) {
    return true;
  }
  return false;
}

class _DenseGrid extends ConsumerWidget {
  const _DenseGrid({required this.schema, required this.state, this.users});

  final PageSchema schema;
  final RecordListState state;
  final List<User>? users;

  String _enteredBy(String userId) {
    final list = users;
    if (list == null) return '—';
    for (final user in list) {
      if (user.id == userId) return user.fullName;
    }
    return '—';
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    if (state.isLoading && state.items.isEmpty) {
      return const AppLoadingState();
    }
    if (state.error != null && state.items.isEmpty) {
      return AppErrorState(message: state.error!.detail);
    }
    if (state.items.isEmpty) {
      final isFiltered =
          state.query.filters.isNotEmpty ||
          (state.query.search?.isNotEmpty ?? false);
      if (isFiltered) {
        return EmptyState.filtered(
          onClear: () => ref
              .read(recordListControllerProvider(schema.page.id).notifier)
              .applyQuery(filters: const [], sort: const [], clearSearch: true),
        );
      }
      return const EmptyState(
        title: 'No records yet',
        message: 'Tap Add record to enter the first one.',
      );
    }

    final columns = tableColumnsFor(schema);
    final lastIndex = state.items.length - 1;
    final lastCell = columns.length + 1;
    final rightAligned = <int>{
      for (var i = 0; i < columns.length; i++)
        if (_isNumeric(columns[i])) i + 1,
    };

    return _LoadMoreListener(
      pageId: schema.page.id,
      hasMore: state.hasMore,
      child: LayoutBuilder(
        builder: (context, constraints) {
          final minWidth = _minTableWidth(columns);
          final tableWidth = constraints.maxWidth > minWidth
              ? constraints.maxWidth
              : minWidth;
          return ListView(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.md,
              AppSpacing.lg,
              AppSpacing.lg,
            ),
            children: [
              SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                child: SizedBox(
                  width: tableWidth,
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      color: AppColors.surface,
                      border: Border.all(color: AppColors.border),
                      borderRadius: AppRadii.mdRadius,
                    ),
                    child: ClipRRect(
                      borderRadius: AppRadii.mdRadius,
                      child: Table(
                        columnWidths: _tableWidths(columns),
                        defaultVerticalAlignment:
                            TableCellVerticalAlignment.middle,
                        children: [
                          _schemaTableRow(
                            isHeader: true,
                            lastCell: lastCell,
                            rightAligned: rightAligned,
                            cells: [
                              _headerCell('Date'),
                              for (final column in columns)
                                _headerCell(
                                  column.name,
                                  numeric: _isNumeric(column),
                                ),
                              _headerCell('Entered by'),
                            ],
                          ),
                          for (var i = 0; i < state.items.length; i++)
                            _schemaTableRow(
                              isHeader: false,
                              striped: i.isOdd,
                              last: i == lastIndex,
                              lastCell: lastCell,
                              rightAligned: rightAligned,
                              onTap: () => context.pushNamed(
                                'recordDetail',
                                pathParameters: {'recordId': state.items[i].id},
                              ),
                              cells: [
                                Text(
                                  _tableDate(state.items[i].businessDate),
                                  style: _dateStyle,
                                ),
                                for (final column in columns)
                                  _valueCell(column, state.items[i]),
                                Text(
                                  _enteredBy(state.items[i].createdBy),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                  style: _enteredStyle,
                                ),
                              ],
                            ),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

const _headerStyle = TextStyle(
  fontSize: 11.5,
  fontWeight: FontWeight.w600,
  height: 1.15,
  color: AppColors.textSecondary,
);
const _dateStyle = TextStyle(
  fontSize: 13,
  height: 1.2,
  color: AppColors.textSecondary,
);
const _nameStyle = TextStyle(
  fontSize: 13,
  fontWeight: FontWeight.w500,
  height: 1.2,
  color: AppColors.textPrimary,
);
const _enteredStyle = TextStyle(
  fontSize: 13,
  height: 1.2,
  color: AppColors.textTertiary,
);
const _amountStyle = TextStyle(
  fontSize: 13,
  fontWeight: FontWeight.w600,
  height: 1,
  color: AppColors.textPrimary,
);

bool _isNumeric(PageColumn column) => switch (column.dataType) {
  ColumnType.currency ||
  ColumnType.number ||
  ColumnType.percent ||
  ColumnType.formula => true,
  _ => false,
};

Widget _headerCell(String label, {bool numeric = false}) {
  return Text(
    label,
    maxLines: 2,
    overflow: TextOverflow.ellipsis,
    style: _headerStyle,
    textAlign: numeric ? TextAlign.right : TextAlign.left,
  );
}

Widget _valueCell(PageColumn column, PageRecord record) {
  final value = record.valueFor(column);
  switch (column.dataType) {
    case ColumnType.currency:
    case ColumnType.formula:
      if (value == null || (value is String && value.isEmpty)) {
        return const Text('—', style: TextStyle(color: AppColors.textDisabled));
      }
      return AmountText(value, style: _amountStyle);
    case ColumnType.select:
      return Text(
        formatRecordValue(column, value),
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: _nameStyle,
      );
    case ColumnType.date:
      final text = _tableDate(value);
      return Text(text.isEmpty ? '—' : text, style: _dateStyle);
    case ColumnType.longText:
      final text = formatRecordValue(column, value);
      return Text(
        text,
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
        style: _dateStyle.copyWith(
          height: 1.25,
          color: text == '—' ? AppColors.textDisabled : AppColors.textSecondary,
        ),
      );
    default:
      return Text(
        formatRecordValue(column, value),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
        style: _isNumeric(column) ? _amountStyle : _nameStyle,
      );
  }
}

Map<int, TableColumnWidth> _tableWidths(List<PageColumn> columns) {
  final widths = <int, TableColumnWidth>{0: const FixedColumnWidth(110)};
  for (var i = 0; i < columns.length; i++) {
    widths[i + 1] = switch (columns[i].dataType) {
      ColumnType.currency ||
      ColumnType.number ||
      ColumnType.percent ||
      ColumnType.formula => const FixedColumnWidth(120),
      ColumnType.longText => const FlexColumnWidth(1.2),
      ColumnType.select || ColumnType.boolean => const FixedColumnWidth(110),
      _ => const FlexColumnWidth(1),
    };
  }
  widths[columns.length + 1] = const FixedColumnWidth(130);
  return widths;
}

double _minTableWidth(List<PageColumn> columns) {
  var width = 110.0 + 130.0;
  for (final column in columns) {
    width += switch (column.dataType) {
      ColumnType.currency ||
      ColumnType.number ||
      ColumnType.percent ||
      ColumnType.formula => 120,
      ColumnType.select || ColumnType.boolean => 110,
      ColumnType.longText => 160,
      _ => 140,
    };
  }
  return width;
}

final DateFormat _tableDateFormat = DateFormat('dd MMM yyyy');

String _tableDate(Object? value) {
  final parsed = parseWireDate(value);
  return parsed == null ? '' : _tableDateFormat.format(parsed);
}

TableRow _schemaTableRow({
  required bool isHeader,
  required List<Widget> cells,
  required int lastCell,
  required Set<int> rightAligned,
  bool striped = false,
  bool last = false,
  VoidCallback? onTap,
}) {
  Widget pad(int index, Widget child) {
    final right = rightAligned.contains(index);
    return Padding(
      padding: EdgeInsets.fromLTRB(
        index == 0 ? 14 : 6,
        isHeader ? 11 : 13,
        index == lastCell ? 14 : 6,
        isHeader ? 11 : 13,
      ),
      child: right
          ? SizedBox(
              width: double.infinity,
              child: Align(alignment: Alignment.centerRight, child: child),
            )
          : child,
    );
  }

  return TableRow(
    decoration: BoxDecoration(
      color: isHeader
          ? AppColors.surfaceSubtle
          : (striped ? AppColors.background : AppColors.surface),
      border: last
          ? null
          : Border(
              bottom: BorderSide(
                color: isHeader ? AppColors.border : AppColors.hairline,
              ),
            ),
    ),
    children: [
      for (var i = 0; i < cells.length; i++)
        isHeader || onTap == null
            ? pad(i, cells[i])
            : TableRowInkWell(onTap: onTap, child: pad(i, cells[i])),
    ],
  );
}

class _DesktopRecordsHeader extends StatelessWidget {
  const _DesktopRecordsHeader({
    required this.title,
    required this.search,
    required this.filterActive,
    required this.onSearch,
    required this.onFilter,
    required this.onAdd,
    this.subtitle,
  });

  final String title;
  final String? subtitle;
  final TextEditingController search;
  final bool filterActive;
  final VoidCallback onSearch;
  final VoidCallback onFilter;
  final VoidCallback onAdd;

  @override
  Widget build(BuildContext context) {
    final titleBlock = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // `titleLarge` is already 18/700/textPrimary — an exact match.
        Text(title, style: Theme.of(context).textTheme.titleLarge),
        if (subtitle != null) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            subtitle!,
            style: Theme.of(context).textTheme.bodySmall
                ?.copyWith(color: AppColors.textTertiary, height: 1.35),
          ),
        ],
      ],
    );
    final actions = [
      _SearchPill(controller: search, onSubmitted: (_) => onSearch()),
      _HeaderChip(
        icon: Icons.filter_list,
        label: 'Filter',
        active: filterActive,
        onTap: onFilter,
      ),
      _AddRecordChip(onTap: onAdd),
    ];

    return Material(
      color: AppColors.surface,
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              AppSpacing.smMd,
              AppSpacing.lg,
              AppSpacing.smMd,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final stacked = constraints.maxWidth < 640;
                if (stacked) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      titleBlock,
                      const SizedBox(height: AppSpacing.smMd),
                      Wrap(
                        spacing: AppSpacing.sm,
                        runSpacing: AppSpacing.sm,
                        children: actions,
                      ),
                    ],
                  );
                }
                return Row(
                  children: [
                    Expanded(child: titleBlock),
                    for (var i = 0; i < actions.length; i++) ...[
                      if (i > 0) const SizedBox(width: AppSpacing.sm),
                      actions[i],
                    ],
                  ],
                );
              },
            ),
          ),
          const Divider(height: 1, color: AppColors.border),
        ],
      ),
    );
  }
}

class _SearchPill extends StatelessWidget {
  const _SearchPill({required this.controller, required this.onSubmitted});

  final TextEditingController controller;
  final ValueChanged<String> onSubmitted;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 148,
      height: 44,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.smMd),
      decoration: BoxDecoration(
        color: AppColors.surface,
        border: Border.all(color: AppColors.border),
        borderRadius: AppRadii.smRadius,
      ),
      child: Row(
        children: [
          const Icon(Icons.search, size: 15, color: AppColors.textTertiary),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: TextField(
              controller: controller,
              textInputAction: TextInputAction.search,
              autocorrect: false,
              style: Theme.of(context).textTheme.bodySmall
                  ?.copyWith(height: 1.2, color: AppColors.textPrimary),
              decoration: InputDecoration(
                isCollapsed: true,
                border: InputBorder.none,
                enabledBorder: InputBorder.none,
                focusedBorder: InputBorder.none,
                filled: false,
                hintText: 'Search',
                hintStyle: Theme.of(context).textTheme.bodySmall
                    ?.copyWith(color: AppColors.textDisabled),
              ),
              onSubmitted: onSubmitted,
            ),
          ),
        ],
      ),
    );
  }
}

class _HeaderChip extends StatelessWidget {
  const _HeaderChip({
    required this.icon,
    required this.label,
    required this.onTap,
    this.active = false,
  });

  final IconData icon;
  final String label;
  final VoidCallback onTap;
  final bool active;

  @override
  Widget build(BuildContext context) {
    // `active` must never be color-alone (design.md §4.3): the border tint
    // already changes, but a colorblind or screen-reader user needs a
    // non-color cue too — the tooltip states it in words, and a small dot
    // renders next to the icon.
    return Tooltip(
      message: active ? '$label (active)' : label,
      child: Material(
        color: active ? AppColors.brandPrimarySoft : AppColors.surface,
        shape: RoundedRectangleBorder(
          borderRadius: AppRadii.smRadius,
          side: BorderSide(
            color: active ? AppColors.brandPrimaryDark : AppColors.border,
          ),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: AppRadii.smRadius,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.smMd),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(icon, size: 15, color: AppColors.textSecondary),
                  const SizedBox(width: AppSpacing.sm),
                  // `titleSmall` is already 12/600/textSecondary — a match.
                  Text(label, style: Theme.of(context).textTheme.titleSmall),
                  if (active) ...[
                    const SizedBox(width: AppSpacing.sm),
                    const Icon(
                      Icons.circle,
                      size: 6,
                      color: AppColors.brandPrimaryDark,
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _AddRecordChip extends StatelessWidget {
  const _AddRecordChip({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: 'Add record',
      child: Material(
        color: AppColors.brandPrimaryDark,
        borderRadius: AppRadii.smRadius,
        child: InkWell(
          onTap: onTap,
          borderRadius: AppRadii.smRadius,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: AppSpacing.md),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.add, size: 15, color: AppColors.textOnBrand),
                  const SizedBox(width: AppSpacing.sm),
                  // `bodyMedium` is already 14/600 — only color differs.
                  Text(
                    'Add record',
                    style: Theme.of(context).textTheme.bodyMedium
                        ?.copyWith(color: AppColors.textOnBrand),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
