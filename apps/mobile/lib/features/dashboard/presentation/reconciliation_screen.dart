import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/adaptive_scaffold.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/app_data_table.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/app_status_chip.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/refreshable.dart';
import '../application/dashboard_providers.dart';
import '../domain/reconciliation.dart';

/// Daily Revenue vs Cash Ledger, per business date (plan section 3.5.11,
/// docs/API.md §1.8) — the one workflow the generic page engine can't
/// express on its own. A plain pushed route, own `Scaffold`, not one of the
/// shell's tabs (plan section 22.4 fixes those at Home/Pages/More).
class ReconciliationScreen extends ConsumerWidget {
  const ReconciliationScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final itemsAsync = ref.watch(reconciliationProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Reconciliation')),
      body: itemsAsync.when(
        data: (items) => _ReconciliationList(
          items: items,
          onRefresh: () async => ref.invalidate(reconciliationProvider),
        ),
        loading: () => PullToRefresh(
          onRefresh: () async => ref.invalidate(reconciliationProvider),
          child: const AppLoadingState(message: 'Loading reconciliation'),
        ),
        error: (error, _) {
          if (error is ApiException && error.isNotFound) {
            return PullToRefresh(
              onRefresh: () async => ref.invalidate(reconciliationProvider),
              child: const EmptyState(
                icon: Icons.balance_outlined,
                title: 'Not available',
                message:
                    'Reconciliation isn\'t available. Ask the Owner for access to '
                    'Daily Revenue and Cash Ledger.',
              ),
            );
          }
          return PullToRefresh(
            onRefresh: () async => ref.invalidate(reconciliationProvider),
            child: AppErrorState(
              message: '$error',
              onRetry: () => ref.invalidate(reconciliationProvider),
            ),
          );
        },
      ),
    );
  }
}

class _ReconciliationList extends StatelessWidget {
  const _ReconciliationList({required this.items, required this.onRefresh});

  final List<ReconciliationItem> items;
  final Future<void> Function() onRefresh;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return PullToRefresh(
        onRefresh: onRefresh,
        child: const EmptyState(
          icon: Icons.balance_outlined,
          message: 'No Daily Revenue or Cash Ledger entries yet.',
        ),
      );
    }

    return PullToRefresh(
      onRefresh: onRefresh,
      childScrolls: true,
      child: LayoutBuilder(
        builder: (context, constraints) {
          if (AdaptiveScaffold.isExpanded(constraints.maxWidth)) {
            return ListView(
              padding: const EdgeInsets.all(AppSpacing.md),
              children: [
                AppDataTable(
                  columns: const [
                    DataColumn(label: Text('Date')),
                    DataColumn(label: Text('Revenue'), numeric: true),
                    DataColumn(label: Text('Ledger'), numeric: true),
                    DataColumn(label: Text('Difference'), numeric: true),
                    DataColumn(label: Text('Status')),
                  ],
                  rows: [
                    for (final item in items)
                      DataRow(
                        cells: [
                          DataCell(Text(formatDate(item.businessDate))),
                          DataCell(AmountText(item.revenueTotal)),
                          DataCell(AmountText(item.ledgerTotal)),
                          DataCell(
                            AmountText(
                              item.difference,
                              colorByValue: !item.matches,
                            ),
                          ),
                          DataCell(
                            AppStatusChip.reconciliation(matches: item.matches),
                          ),
                        ],
                      ),
                  ],
                ),
              ],
            );
          }
          return ListView.separated(
            padding: const EdgeInsets.all(AppSpacing.md),
            itemCount: items.length,
            separatorBuilder: (context, index) =>
                const SizedBox(height: AppSpacing.sm),
            itemBuilder: (context, index) =>
                _ReconciliationRow(item: items[index]),
          );
        },
      ),
    );
  }
}

class _ReconciliationRow extends StatelessWidget {
  const _ReconciliationRow({required this.item});

  final ReconciliationItem item;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;

    return AppCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(formatDate(item.businessDate), style: textTheme.titleMedium),
              AppStatusChip.reconciliation(matches: item.matches),
            ],
          ),
          const SizedBox(height: AppSpacing.sm),
          const Divider(height: 1, color: AppColors.hairline),
          const SizedBox(height: AppSpacing.sm),
          Row(
            children: [
              Expanded(
                child: _Figure(label: 'Revenue', value: item.revenueTotal),
              ),
              Expanded(
                child: _Figure(label: 'Ledger', value: item.ledgerTotal),
              ),
              Expanded(
                child: _Figure(
                  label: 'Difference',
                  value: item.difference,
                  emphasize: !item.matches,
                  alignment: CrossAxisAlignment.end,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Figure extends StatelessWidget {
  const _Figure({
    required this.label,
    required this.value,
    this.emphasize = false,
    this.alignment = CrossAxisAlignment.start,
  });

  final String label;
  final Object value;
  final bool emphasize;
  final CrossAxisAlignment alignment;

  @override
  Widget build(BuildContext context) {
    // A reconciliation difference is "attention", not "blocking" (design.md
    // §4.1's color-role table) — warning-tinted, not the same red used for
    // a failed request.
    final valueStyle = Theme.of(context).textTheme.bodyLarge?.copyWith(
      fontWeight: emphasize ? FontWeight.bold : FontWeight.normal,
      color: emphasize ? AppColors.warning : null,
    );

    return Column(
      crossAxisAlignment: alignment,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        AmountText(value, style: valueStyle),
      ],
    );
  }
}
