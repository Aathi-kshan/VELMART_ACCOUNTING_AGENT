import 'package:dio/dio.dart';

import '../../../core/date/business_date.dart';
import '../../../core/network/api_exception.dart';
import '../domain/reconciliation.dart';
import '../domain/widget.dart';

/// `GET /reconciliation` (plan section 3.5.11, docs/API.md §1.8) and
/// dashboard widget CRUD/evaluation (plan section 15, P5). Thin, like
/// `PageRepository`: no validation, no decisions, just send and parse.
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

  // --- widgets (P5) ---------------------------------------------------

  /// Already filtered server-side for a manager (`visible_to` role AND page
  /// view-access, `app/services/dashboard_service.py`'s double gate) — this
  /// renders whatever comes back, same as every other 🟡 filtered list.
  Future<List<DashboardWidget>> listWidgets() => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/dashboard/widgets');
    return response.data!.cast<Map<String, dynamic>>().map(DashboardWidget.fromJson).toList();
  });

  Future<DashboardWidget> createWidget({
    required String title,
    required WidgetType widgetType,
    required String pageKey,
    Map<String, dynamic> config = const {},
    int position = 0,
    String? visibleTo,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/dashboard/widgets',
      data: {
        'title': title,
        'widget_type': widgetType.wire,
        'page_key': pageKey,
        'config': config,
        'position': position,
        if (visibleTo != null) 'visible_to': visibleTo,
      },
    );
    return DashboardWidget.fromJson(response.data!);
  });

  Future<DashboardWidget> updateWidget(
    String widgetId, {
    String? title,
    Map<String, dynamic>? config,
    int? position,
    String? visibleTo,
    bool clearVisibleTo = false,
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/dashboard/widgets/$widgetId',
      data: {
        if (title != null) 'title': title,
        if (config != null) 'config': config,
        if (position != null) 'position': position,
        if (visibleTo != null) 'visible_to': visibleTo,
        'clear_visible_to': clearVisibleTo,
      },
    );
    return DashboardWidget.fromJson(response.data!);
  });

  Future<void> deleteWidget(String widgetId) =>
      mapApiErrors(() async => dio.delete<void>('/dashboard/widgets/$widgetId'));

  Future<WidgetEvaluation> getWidgetData(String widgetId) => mapApiErrors(() async {
    final response = await dio.get<Map<String, dynamic>>('/dashboard/widgets/$widgetId/data');
    return WidgetEvaluation.fromJson(response.data!);
  });

  Future<List<WidgetSuggestion>> getSuggestions() => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/dashboard/suggestions');
    return response.data!.cast<Map<String, dynamic>>().map(WidgetSuggestion.fromJson).toList();
  });
}
