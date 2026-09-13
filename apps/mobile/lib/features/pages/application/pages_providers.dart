/// Read-only data — one `FutureProvider` per query, matching the plan's
/// stated deviation from P1's hand-rolled `sealed` state: a fetch that
/// either succeeds or fails, with no further steps in between, is exactly
/// what `AsyncValue` already models. Writes and paginated lists (which
/// accumulate state across calls) keep the `StateNotifier` shape instead —
/// see `record_list_controller.dart`.
library;

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/providers.dart';
import '../../auth/domain/user.dart';
import '../data/page_repository.dart';
import '../domain/csv_import.dart';
import '../domain/page.dart';
import '../domain/store.dart';

final pageRepositoryProvider = Provider<PageRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return PageRepository(dio: client.dio);
});

/// Every page visible to the caller — the server already filters a manager
/// down to their granted pages (plan section 4.3); this renders whatever
/// comes back, nothing more.
final pagesProvider = FutureProvider<List<Page>>((ref) {
  return ref.watch(pageRepositoryProvider).listPages();
});

final pageSchemaProvider = FutureProvider.family<PageSchema, String>((ref, pageId) {
  return ref.watch(pageRepositoryProvider).getSchema(pageId);
});

/// Feeds `STORE_REF` pickers and, later, a store filter.
final storesProvider = FutureProvider<List<Store>>((ref) {
  return ref.watch(pageRepositoryProvider).listStores();
});

/// Feeds `USER_REF` pickers and the access editor's manager list. Owner-only
/// on the server — a manager's `AsyncValue` here resolves to an error, which
/// callers treat as "no directory available" rather than surfacing a scary
/// exception (see the `USER_REF` renderer).
final usersProvider = FutureProvider<List<User>>((ref) {
  return ref.watch(pageRepositoryProvider).listUsers();
});

/// Recent CSV import batches for one page (plan section 13.1) — feeds the
/// rollback history list in `csv_import_screen.dart`.
final importBatchesProvider = FutureProvider.family<List<ImportBatch>, String>((ref, pageId) {
  return ref.watch(pageRepositoryProvider).listImportBatches(pageId);
});
