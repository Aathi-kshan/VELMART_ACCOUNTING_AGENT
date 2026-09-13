import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/dashboard_repository.dart';
import '../domain/reconciliation.dart';
import '../domain/widget.dart';

final dashboardRepositoryProvider = Provider<DashboardRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return DashboardRepository(dio: client.dio);
});

/// The full reconciliation history — no date filter. A manager missing
/// `view` on either `daily_revenue` or `cash_ledger` resolves to an
/// `AsyncError` (a 404 via `ApiException`), which `reconciliation_screen.dart`
/// renders as an informational "not available" state rather than a scary
/// error, matching how `usersProvider` treats a manager's 403.
final reconciliationProvider = FutureProvider<List<ReconciliationItem>>((ref) {
  return ref.watch(dashboardRepositoryProvider).getReconciliation();
});

/// Every widget the caller can see, already server-filtered (P5). Invalidate
/// after an update/delete to refetch — `home_screen.dart` does this rather
/// than hand-patching the list locally.
final dashboardWidgetsProvider = FutureProvider<List<DashboardWidget>>((ref) {
  return ref.watch(dashboardRepositoryProvider).listWidgets();
});

/// One widget's live data — keyed by id so `home_screen.dart` can watch
/// several independently and only the one that changed re-fetches.
final widgetDataProvider = FutureProvider.family<WidgetEvaluation, String>((ref, widgetId) {
  return ref.watch(dashboardRepositoryProvider).getWidgetData(widgetId);
});
