import 'package:dio/dio.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../domain/reconciliation.dart';

/// `GET /reconciliation` (plan section 3.5.11, docs/API.md §1.8). Thin,
/// like `PageRepository`: no validation, no decisions, just send and
/// parse.
///
/// The dashboard-widget methods that used to live here were removed with
/// the feature: no code path anywhere could create a widget, so the list
/// was always empty and the endpoints backing these calls are gone.
class DashboardRepository {
  DashboardRepository({required this.dio});

  final Dio dio;

  /// A manager missing `view` on either `daily_revenue` or `cash_ledger`
  /// gets a 404 here — the caller renders that as "not available", not an
  /// error (see `reconciliation_screen.dart`).
  Future<List<ReconciliationItem>> getReconciliation({DateTime? from, DateTime? to}) =>
      mapApiErrors(() async {
        final response = await dio.get<Map<String, dynamic>>(
          '/reconciliation',
          queryParameters: {
            if (from != null) 'from': toWireDate(from),
            if (to != null) 'to': toWireDate(to),
          },
        );
        return (response.data!['items'] as List<dynamic>)
            .cast<Map<String, dynamic>>()
            .map(ReconciliationItem.fromJson)
            .toList();
      });
}
