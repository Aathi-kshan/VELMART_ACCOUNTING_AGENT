import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/date/business_date.dart';
import '../../../core/money/money.dart';
import '../../../core/network/api_exception.dart';
import '../../dashboard/application/dashboard_providers.dart';
import '../../dashboard/domain/reconciliation.dart';
import '../../pages/application/pages_providers.dart';
import '../../pages/domain/page.dart';
import '../../pages/domain/record.dart';

class HomeDashboard {
  const HomeDashboard({
    required this.todayLabel,
    this.revenuePageId,
    this.expensesPageId,
    this.purchasesPageId,
    this.purchasesPageName,
    this.chequesPageId,
    this.todayRevenue,
    this.previousRevenue,
    this.cashSales,
    this.cardSales,
    this.todayRecordCount = 0,
    this.mismatch,
    this.monthExpenses,
    this.lastMonthExpenses,
    this.monthPurchases,
    this.lastMonthPurchases,
    this.expenseBreakdown = const [],
    this.pendingCheques = const [],
    this.pendingCount = 0,
    this.chequesTotalCount = 0,
  });

  final String todayLabel;
  final String? revenuePageId;
  final String? expensesPageId;
  final String? purchasesPageId;

  /// The page's own display name (e.g. "Purchases for Cash") — read this
  /// rather than hardcoding a label, so a rename on the backend can never
  /// leave a stale string behind here.
  final String? purchasesPageName;
  final String? chequesPageId;
  final Money? todayRevenue;
  final Money? previousRevenue;
  final Money? cashSales;
  final Money? cardSales;
  final int todayRecordCount;
  final ReconciliationItem? mismatch;
  final Money? monthExpenses;
  final Money? lastMonthExpenses;
  final Money? monthPurchases;
  final Money? lastMonthPurchases;
  final List<AggregateGroup> expenseBreakdown;
  final List<PageRecord> pendingCheques;
  final int pendingCount;
  final int chequesTotalCount;

  double? percentChange(Money? current, Money? previous) {
    if (current == null || previous == null || previous.isZero) return null;
    return (current.minorUnits - previous.minorUnits) / previous.minorUnits * 100;
  }
}

final homeDashboardProvider = FutureProvider<HomeDashboard>((ref) async {
  final repo = ref.watch(pageRepositoryProvider);
  final dash = ref.watch(dashboardRepositoryProvider);
  final pages = await ref.watch(pagesProvider.future);

  Page? byKey(String key) {
    for (final page in pages) {
      if (page.key == key) return page;
    }
    return null;
  }

  final revenue = byKey('daily_revenue');
  final expenses = byKey('expenses');
  final purchases = byKey('purchases');
  final cheques = byKey('cheques');

  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final lastWeek = today.subtract(const Duration(days: 7));
  final weekdayNames = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];
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
  final todayLabel =
      '${weekdayNames[today.weekday - 1]} ${today.day} ${months[today.month - 1]} · as of '
      '${now.hour.toString().padLeft(2, '0')}:${now.minute.toString().padLeft(2, '0')}';

  final todayFilter = [
    RecordFilter(column: 'business_date', op: FilterOp.eq, value: toWireDate(today)),
  ];
  final lastWeekFilter = [
    RecordFilter(column: 'business_date', op: FilterOp.eq, value: toWireDate(lastWeek)),
  ];

  Future<Money?> sum(
    String? pageId,
    String column, {
    String period = 'all_time',
    List<RecordFilter> filters = const [],
  }) async {
    if (pageId == null) return null;
    try {
      final result = await repo.aggregate(
        pageId,
        AggregateQuery(metric: AggregateMetric.sum, column: column, period: period, filters: filters),
      );
      return Money.parse(result.value);
    } on ApiException {
      return null;
    }
  }

  Future<int> count(String? pageId, {List<RecordFilter> filters = const []}) async {
    if (pageId == null) return 0;
    try {
      final result = await repo.aggregate(
        pageId,
        AggregateQuery(metric: AggregateMetric.count, filters: filters),
      );
      return result.recordCount;
    } on ApiException {
      return 0;
    }
  }

  Money? todayTotal;
  Money? prevTotal;
  Money? cash;
  Money? card;
  var todayCount = 0;
  if (revenue != null) {
    todayCount = await count(revenue.id, filters: todayFilter);
    if (todayCount > 0) {
      todayTotal = await sum(revenue.id, 'total_revenue', filters: todayFilter);
      cash = await sum(revenue.id, 'cash_sales', filters: todayFilter);
      card = await sum(revenue.id, 'card_sales', filters: todayFilter);
      if (todayTotal == null && cash != null && card != null) {
        todayTotal = cash + card;
      }
    }
    prevTotal = await sum(revenue.id, 'total_revenue', filters: lastWeekFilter);
  }

  ReconciliationItem? mismatch;
  try {
    final items = await dash.getReconciliation(
      from: today.subtract(const Duration(days: 14)),
      to: today,
    );
    for (final item in items) {
      if (!item.matches) {
        mismatch = item;
        break;
      }
    }
  } on ApiException {
    mismatch = null;
  }

  final monthExpenses = await sum(expenses?.id, 'amount', period: 'current_month');
  final lastMonthExpenses = await sum(expenses?.id, 'amount', period: 'last_month');
  final monthPurchases = await sum(purchases?.id, 'total_amount', period: 'current_month');
  final lastMonthPurchases = await sum(purchases?.id, 'total_amount', period: 'last_month');

  var breakdown = <AggregateGroup>[];
  if (expenses != null) {
    try {
      final grouped = await repo.aggregate(
        expenses.id,
        const AggregateQuery(
          metric: AggregateMetric.sum,
          column: 'amount',
          groupBy: 'expense_name',
          period: 'current_month',
        ),
      );
      breakdown = [...grouped.groups]..sort((a, b) {
        final av = Money.parse(a.value);
        final bv = Money.parse(b.value);
        return bv.minorUnits.compareTo(av.minorUnits);
      });
    } on ApiException {
      breakdown = const [];
    }
  }

  var pending = <PageRecord>[];
  var pendingCount = 0;
  var chequesTotal = 0;
  if (cheques != null) {
    const pendingFilter = [
      RecordFilter(column: 'cheque_status', op: FilterOp.eq, value: 'PENDING'),
    ];
    pendingCount = await count(cheques.id, filters: pendingFilter);
    chequesTotal = await count(cheques.id);
    try {
      final result = await repo.queryRecords(
        cheques.id,
        const RecordQuery(filters: pendingFilter, limit: 3),
      );
      pending = result.items;
    } on ApiException {
      pending = const [];
    }
  }

  return HomeDashboard(
    todayLabel: todayLabel,
    revenuePageId: revenue?.id,
    expensesPageId: expenses?.id,
    purchasesPageId: purchases?.id,
    purchasesPageName: purchases?.name,
    chequesPageId: cheques?.id,
    todayRevenue: todayTotal,
    previousRevenue: prevTotal,
    cashSales: cash,
    cardSales: card,
    todayRecordCount: todayCount,
    mismatch: mismatch,
    monthExpenses: monthExpenses,
    lastMonthExpenses: lastMonthExpenses,
    monthPurchases: monthPurchases,
    lastMonthPurchases: lastMonthPurchases,
    expenseBreakdown: breakdown,
    pendingCheques: pending,
    pendingCount: pendingCount,
    chequesTotalCount: chequesTotal,
  );
});
