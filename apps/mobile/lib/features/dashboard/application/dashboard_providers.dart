import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../data/dashboard_repository.dart';
import '../domain/reconciliation.dart';

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
