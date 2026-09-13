import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/providers.dart';
import '../data/audit_repository.dart';
import '../domain/audit_log_entry.dart';

final auditRepositoryProvider = Provider<AuditRepository>((ref) {
  final client = ref.watch(apiClientProvider);
  return AuditRepository(dio: client.dio);
});

/// The current filter set — `audit_screen.dart`'s filter bar writes here;
/// [auditLogControllerProvider] watches it and starts over from the first
/// page whenever it changes.
final auditLogFiltersProvider = StateProvider<AuditLogFilters>((ref) => const AuditLogFilters());

/// Accumulated pages of the audit feed — a `StateNotifier`, not a plain
/// `FutureProvider`, for the same reason `record_list_controller.dart` is:
/// "load more" appends to an existing list rather than recomputing it.
final auditLogControllerProvider =
    StateNotifierProvider<AuditLogController, AuditLogState>((ref) {
      final repository = ref.watch(auditRepositoryProvider);
      final filters = ref.watch(auditLogFiltersProvider);
      return AuditLogController(repository, filters);
    });

class AuditLogState {
  const AuditLogState({
    this.items = const [],
    this.cursor,
    this.isLoading = false,
    this.isLoadingMore = false,
    this.hasMore = false,
    this.error,
  });

  final List<AuditLogEntry> items;
  final String? cursor;
  final bool isLoading;
  final bool isLoadingMore;
  final bool hasMore;
  final ApiException? error;

  AuditLogState copyWith({
    List<AuditLogEntry>? items,
    String? cursor,
    bool clearCursor = false,
    bool? isLoading,
    bool? isLoadingMore,
    bool? hasMore,
    ApiException? error,
    bool clearError = false,
  }) => AuditLogState(
    items: items ?? this.items,
    cursor: clearCursor ? null : (cursor ?? this.cursor),
    isLoading: isLoading ?? this.isLoading,
    isLoadingMore: isLoadingMore ?? this.isLoadingMore,
    hasMore: hasMore ?? this.hasMore,
    error: clearError ? null : (error ?? this.error),
  );
}

class AuditLogController extends StateNotifier<AuditLogState> {
  AuditLogController(this._repository, this._filters) : super(const AuditLogState()) {
    _load(reset: true);
  }

  final AuditRepository _repository;
  final AuditLogFilters _filters;

  Future<void> _load({required bool reset}) async {
    if (reset) {
      state = state.copyWith(isLoading: true, clearError: true);
    } else {
      state = state.copyWith(isLoadingMore: true, clearError: true);
    }

    try {
      final page = await _repository.listAuditLogs(
        filters: _filters,
        cursor: reset ? null : state.cursor,
      );
      state = state.copyWith(
        items: reset ? page.items : [...state.items, ...page.items],
        cursor: page.nextCursor,
        clearCursor: page.nextCursor == null,
        hasMore: page.hasMore,
        isLoading: false,
        isLoadingMore: false,
      );
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: e);
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoading || state.isLoadingMore) return;
    await _load(reset: false);
  }

  Future<void> refresh() => _load(reset: true);
}
