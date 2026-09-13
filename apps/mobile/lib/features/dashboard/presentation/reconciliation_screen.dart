import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/empty_state.dart';
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
        data: (items) => _ReconciliationList(items: items),
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) {
          // A manager missing `view` on either daily_revenue or cash_ledger
          // gets a 404 (docs/API.md §1.4) — that's "not available to you",
          // not a broken screen.
          if (error is ApiException && error.isNotFound) {
            return const EmptyState(
              icon: Icons.balance_outlined,
              message:
                  'Reconciliation isn\'t available. Ask the Owner for access to '
                  'Daily Revenue and Cash Ledger.',
            );
          }
          return Center(child: Text('Could not load reconciliation.\n$error'));
        },
      ),
    );
  }
}

class _ReconciliationList extends StatelessWidget {
  const _ReconciliationList({required this.items});

  final List<ReconciliationItem> items;

  @override
  Widget build(BuildContext context) {
    if (items.isEmpty) {
      return const EmptyState(
        icon: Icons.balance_outlined,
        message: 'No Daily Revenue or Cash Ledger entries yet.',
      );
    }

    return ListView.separated(
      padding: const EdgeInsets.all(8),
      itemCount: items.length,
      separatorBuilder: (context, index) => const Divider(height: 1),
      itemBuilder: (context, index) => _ReconciliationRow(item: items[index]),
    );
  }
}

class _ReconciliationRow extends StatelessWidget {
  const _ReconciliationRow({required this.item});

  final ReconciliationItem item;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final textTheme = Theme.of(context).textTheme;

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(formatDate(item.businessDate), style: textTheme.titleMedium),
              if (!item.matches)
                Icon(Icons.warning_amber_rounded, color: colorScheme.error, size: 20),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(child: _Figure(label: 'Revenue', value: item.revenueTotal)),
              Expanded(child: _Figure(label: 'Ledger', value: item.ledgerTotal)),
              Expanded(
                child: _Figure(
                  label: 'Difference',
                  value: item.difference,
                  emphasize: !item.matches,
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
  const _Figure({required this.label, required this.value, this.emphasize = false});

  final String label;
  final Object value;
  final bool emphasize;

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final valueStyle = Theme.of(context).textTheme.bodyLarge?.copyWith(
      fontWeight: emphasize ? FontWeight.bold : FontWeight.normal,
      color: emphasize ? colorScheme.error : null,
    );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: Theme.of(context).textTheme.labelMedium),
        AmountText(value, style: valueStyle),
      ],
    );
  }
}
