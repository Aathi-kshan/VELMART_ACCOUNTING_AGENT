import '../../../core/money/money.dart';

/// One row of `GET /reconciliation` (plan section 3.5.11, docs/API.md §1.8)
/// — `daily_revenue` vs `cash_ledger` for the same business date. A manager
/// needs `view` on both system pages or the whole endpoint 404s; that case
/// is handled by the repository/screen, not represented here.
class ReconciliationItem {
  const ReconciliationItem({
    required this.businessDate,
    required this.revenueTotal,
    required this.ledgerTotal,
    required this.difference,
  });

  factory ReconciliationItem.fromJson(Map<String, dynamic> json) {
    return ReconciliationItem(
      businessDate: json['business_date'] as String,
      revenueTotal: Money.parse(json['revenue_total'] as String),
      ledgerTotal: Money.parse(json['ledger_total'] as String),
      difference: Money.parse(json['difference'] as String),
    );
  }

  /// ISO `yyyy-MM-dd`, matching every other wire-format date in this client.
  final String businessDate;
  final Money revenueTotal;
  final Money ledgerTotal;
  final Money difference;

  bool get matches => difference.minorUnits == 0;
}
