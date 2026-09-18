import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:intl/intl.dart';

import '../../../core/date/business_date.dart';
import '../../../core/money/money.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radii.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/theme/app_typography.dart';
import '../../../core/widgets/amount_text.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/refreshable.dart'; // PullToRefresh
import '../../pages/domain/record.dart';
import '../application/auth_controller.dart';
import '../application/home_providers.dart';
import '../domain/user.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final auth = ref.watch(authControllerProvider);
    final user = auth is AuthAuthenticated ? auth.user : null;
    final dash = ref.watch(homeDashboardProvider);

    if (user == null) return const AppLoadingState();

    return dash.when(
      loading: () => PullToRefresh(
        onRefresh: () async => ref.invalidate(homeDashboardProvider),
        child: const AppLoadingState(),
      ),
      error: (error, _) => PullToRefresh(
        onRefresh: () async => ref.invalidate(homeDashboardProvider),
        child: AppErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(homeDashboardProvider),
        ),
      ),
      data: (data) => PullToRefresh(
        onRefresh: () async => ref.invalidate(homeDashboardProvider),
        childScrolls: true,
        child: _HomeBody(user: user, data: data),
      ),
    );
  }
}

class _HomeBody extends StatelessWidget {
  const _HomeBody({required this.user, required this.data});

  final User user;
  final HomeDashboard data;

  @override
  Widget build(BuildContext context) {
    final initial = user.fullName.isEmpty
        ? '?'
        : user.fullName[0].toUpperCase();
    final now = DateTime.now();
    final lastMonth = DateTime(now.year, now.month - 1, 1);
    final lastMonthName = DateFormat('MMMM').format(lastMonth);

    return ListView(
      physics: const AlwaysScrollableScrollPhysics(),
      padding: const EdgeInsets.only(bottom: AppSpacing.lg),
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.md,
            AppSpacing.smMd,
          ),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Home',
                      style: Theme.of(context).textTheme.headlineLarge,
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      data.todayLabel,
                      style: Theme.of(context).textTheme.labelMedium,
                    ),
                  ],
                ),
              ),
              CircleAvatar(
                radius: 18,
                backgroundColor: AppColors.brandPrimaryDark,
                child: Text(
                  initial,
                  style: Theme.of(context).textTheme.bodyMedium
                      ?.copyWith(color: AppColors.textOnBrand),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            0,
            AppSpacing.md,
            AppSpacing.smMd,
          ),
          child: _RevenueHero(data: data),
        ),
        if (data.mismatch != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              0,
              AppSpacing.md,
              AppSpacing.smMd,
            ),
            child: _MismatchBanner(data: data),
          ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            AppSpacing.xs,
            AppSpacing.md,
            AppSpacing.sm,
          ),
          child: Row(
            children: [
              // `titleSmall` is already 12/600/textSecondary — this label
              // needs no override at all.
              Text('THIS MONTH', style: Theme.of(context).textTheme.titleSmall),
              const Spacer(),
              Text(
                _monthRange(),
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.md,
            0,
            AppSpacing.md,
            AppSpacing.smMd,
          ),
          child: Row(
            children: [
              Expanded(
                child: _MonthMetric(
                  label: 'Total expenses',
                  value: data.monthExpenses,
                  previous: data.lastMonthExpenses,
                  vsLabel: lastMonthName,
                  onTap: data.expensesPageId == null
                      ? null
                      : () => context.pushNamed(
                          'pageRecords',
                          pathParameters: {'pageId': data.expensesPageId!},
                        ),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: _MonthMetric(
                  label: data.purchasesPageName ?? 'Purchases for Cash',
                  value: data.monthPurchases,
                  previous: data.lastMonthPurchases,
                  vsLabel: lastMonthName,
                  onTap: data.purchasesPageId == null
                      ? null
                      : () => context.pushNamed(
                          'pageRecords',
                          pathParameters: {'pageId': data.purchasesPageId!},
                        ),
                ),
              ),
            ],
          ),
        ),
        if (data.expenseBreakdown.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              0,
              AppSpacing.md,
              AppSpacing.smMd,
            ),
            child: _BreakdownCard(groups: data.expenseBreakdown),
          ),
        if (data.pendingCheques.isNotEmpty)
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.md,
              0,
              AppSpacing.md,
              AppSpacing.lg,
            ),
            child: _PendingCheques(
              records: data.pendingCheques,
              pendingCount: data.pendingCount,
              totalCount: data.chequesTotalCount,
            ),
          ),
      ],
    );
  }

  String _monthRange() {
    final now = DateTime.now();
    return '1–${now.day} ${DateFormat('MMMM').format(now)}';
  }
}

class _RevenueHero extends StatelessWidget {
  const _RevenueHero({required this.data});

  final HomeDashboard data;

  @override
  Widget build(BuildContext context) {
    // `titleSmall` is already 12/600/textSecondary — no override needed.
    final labelStyle = Theme.of(context).textTheme.titleSmall;

    if (data.todayRevenue == null) {
      return AppCard(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Total revenue', style: labelStyle),
            const SizedBox(height: AppSpacing.sm),
            Text(
              'No revenue recorded today',
              style: Theme.of(context).textTheme.titleMedium,
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Add a Daily Revenue record to see today’s total here.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ],
        ),
      );
    }

    final pct = data.percentChange(data.todayRevenue, data.previousRevenue);
    final weekday = DateFormat('EEEE').format(DateTime.now());
    final heroStyle = Theme.of(context).textTheme.headlineMedium?.copyWith(
      fontSize: 32,
      height: 1.15,
      letterSpacing: -0.32,
      color: AppColors.textPrimary,
    );

    return AppCard(
      onTap: data.revenuePageId == null
          ? null
          : () => context.pushNamed(
              'pageRecords',
              pathParameters: {'pageId': data.revenuePageId!},
            ),
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Total revenue', style: labelStyle),
          const SizedBox(height: AppSpacing.xs),
          AmountText(data.todayRevenue, style: heroStyle),
          const SizedBox(height: AppSpacing.xs),
          Text(
            [
              'Today',
              '${data.todayRecordCount} record${data.todayRecordCount == 1 ? '' : 's'}',
              if (pct != null)
                '${pct >= 0 ? '+' : '\u2212'}${pct.abs().toStringAsFixed(1)}% vs last $weekday',
            ].join(' · '),
            // `bodySmall` is already 12/400 — only weight/color differ here.
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              fontWeight: FontWeight.w500,
              color: AppColors.textTertiary,
            ),
          ),
          const SizedBox(height: AppSpacing.smMd),
          const Divider(height: 1, color: AppColors.border),
          const SizedBox(height: AppSpacing.smMd),
          Row(
            children: [
              Expanded(
                child: _Split(label: 'Cash sales', value: data.cashSales),
              ),
              Expanded(
                child: _Split(label: 'Card sales', value: data.cardSales),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _Split extends StatelessWidget {
  const _Split({required this.label, required this.value});

  final String label;
  final Money? value;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: Theme.of(context).textTheme.labelMedium
              ?.copyWith(color: AppColors.textTertiary),
        ),
        const SizedBox(height: AppSpacing.xs),
        AmountText(
          value ?? Money.zero,
          // `bodyLarge` is already 14/400 — weight/height differ here.
          style: Theme.of(context).textTheme.bodyLarge?.copyWith(
            color: AppColors.textPrimary,
            fontWeight: FontWeight.w600,
            height: 1,
          ),
        ),
      ],
    );
  }
}

class _MismatchBanner extends StatelessWidget {
  const _MismatchBanner({required this.data});

  final HomeDashboard data;

  @override
  Widget build(BuildContext context) {
    final item = data.mismatch!;
    final date = formatDateLong(item.businessDate);
    return Material(
      color: AppColors.warningSoft,
      shape: RoundedRectangleBorder(
        borderRadius: AppRadii.mdRadius,
        side: const BorderSide(color: AppColors.warningBorder),
      ),
      child: InkWell(
        onTap: () => context.pushNamed('reconciliation'),
        borderRadius: AppRadii.mdRadius,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.md),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Padding(
                padding: EdgeInsets.only(top: 1),
                child: Icon(
                  Icons.warning_amber_rounded,
                  color: AppColors.warning,
                  size: 20,
                ),
              ),
              const SizedBox(width: AppSpacing.smMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Difference of ${item.difference.format()} on $date',
                      style: Theme.of(context).textTheme.bodyLarge?.copyWith(
                        color: AppColors.textPrimary,
                        fontWeight: FontWeight.w600,
                        height: 1.3,
                      ),
                    ),
                    const SizedBox(height: AppSpacing.xs),
                    // `bodySmall` is already 12/400/textSecondary/height 1.4
                    // — an exact match, no override needed.
                    Text(
                      item.difference.isNegative
                          ? 'Daily Revenue is lower than the Cash Ledger. Open reconciliation.'
                          : 'Card sales in the Cash Ledger are lower than Daily Revenue. Open reconciliation.',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _MonthMetric extends StatelessWidget {
  const _MonthMetric({
    required this.label,
    required this.value,
    required this.previous,
    required this.vsLabel,
    this.onTap,
  });

  final String label;
  final Money? value;
  final Money? previous;
  final String vsLabel;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final pct = () {
      if (value == null || previous == null || previous!.isZero) return null;
      return (value!.minorUnits - previous!.minorUnits) /
          previous!.minorUnits *
          100;
    }();
    return AppCard(
      onTap: onTap,
      padding: const EdgeInsets.all(AppSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // `titleSmall` is already 12/600/textSecondary — no override needed.
          Text(label, style: Theme.of(context).textTheme.titleSmall),
          const SizedBox(height: AppSpacing.xs),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: AmountText(
              value ?? Money.zero,
              style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                fontSize: 20,
                height: 1.15,
                color: AppColors.textPrimary,
              ),
            ),
          ),
          if (pct != null) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(
              '${pct >= 0 ? '+' : '\u2212'}${pct.abs().toStringAsFixed(0)}% vs $vsLabel',
              style: Theme.of(context).textTheme.labelMedium?.copyWith(
                color: pct >= 0 ? AppColors.warning : AppColors.success,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _BreakdownCard extends StatelessWidget {
  const _BreakdownCard({required this.groups});

  final List<AggregateGroup> groups;

  @override
  Widget build(BuildContext context) {
    final max = groups
        .map((g) => Money.parse(g.value).minorUnits)
        .fold<int>(0, (a, b) => a > b ? a : b);
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Expenses by name',
                  // `bodyMedium` is already 14/600 — only height differs.
                  style: Theme.of(context).textTheme.bodyMedium
                      ?.copyWith(height: 1),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(
                DateFormat('MMMM').format(DateTime.now()),
                style: Theme.of(context).textTheme.labelMedium,
              ),
            ],
          ),
          const SizedBox(height: AppSpacing.smMd),
          for (final group in groups.take(6)) ...[
            Row(
              crossAxisAlignment: CrossAxisAlignment.baseline,
              textBaseline: TextBaseline.alphabetic,
              children: [
                Expanded(
                  child: Text(
                    group.key,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: AppTypography.data(color: AppColors.textPrimary),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                AmountText(
                  group.value,
                  style: AppTypography.dataStrong(color: AppColors.textPrimary),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            ClipRRect(
              borderRadius: AppRadii.pillRadius,
              child: LinearProgressIndicator(
                minHeight: 8,
                value: max == 0 ? 0 : Money.parse(group.value).minorUnits / max,
                backgroundColor: AppColors.surfaceSubtle,
                color: AppColors.brandPrimary,
              ),
            ),
            const SizedBox(height: AppSpacing.smMd),
          ],
        ],
      ),
    );
  }
}

class _PendingCheques extends StatelessWidget {
  const _PendingCheques({
    required this.records,
    required this.pendingCount,
    required this.totalCount,
  });

  final List<PageRecord> records;
  final int pendingCount;
  final int totalCount;

  @override
  Widget build(BuildContext context) {
    final countLabel = totalCount > 0
        ? '$pendingCount of $totalCount'
        : '$pendingCount';
    return AppCard(
      padding: const EdgeInsets.all(AppSpacing.cardPadding),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  'Pending cheques',
                  // `bodyMedium` is already 14/600 — only height differs.
                  style: Theme.of(context).textTheme.bodyMedium
                      ?.copyWith(height: 1),
                ),
              ),
              const SizedBox(width: AppSpacing.sm),
              Text(countLabel, style: Theme.of(context).textTheme.labelMedium),
            ],
          ),
          const SizedBox(height: AppSpacing.smMd),
          for (final record in records)
            InkWell(
              onTap: () => context.pushNamed(
                'recordDetail',
                pathParameters: {'recordId': record.id},
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(vertical: AppSpacing.sm),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            record.data['payee_name']?.toString() ?? 'Cheque',
                            style: AppTypography.data(
                              color: AppColors.textPrimary,
                            ),
                          ),
                          const SizedBox(height: AppSpacing.xs),
                          Text(
                            _chequeMeta(record),
                            // `bodySmall` is already 12/400/height 1.4 — only
                            // color differs here.
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: AppColors.textTertiary),
                          ),
                        ],
                      ),
                    ),
                    AmountText(
                      record.data['amount'],
                      style: AppTypography.dataStrong(
                        color: AppColors.textPrimary,
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }

  String _chequeMeta(PageRecord record) {
    final number = record.data['cheque_number']?.toString() ?? '';
    final due = formatDate(record.data['cheque_date']);
    final parts = <String>[
      if (number.isNotEmpty) '#$number',
      if (due.isNotEmpty) 'due $due',
    ];
    return parts.join(' · ');
  }
}
