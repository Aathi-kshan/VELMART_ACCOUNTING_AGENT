import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../data/page_repository.dart';
import '../domain/record.dart';
import 'pages_providers.dart';

/// Records for one page: query, loaded items so far, and pagination state.
///
/// A `StateNotifier`, not a `FutureProvider` — "load more" appends to an
/// existing list rather than recomputing it, and changing the filter/sort
/// resets it. That's an imperative sequence of steps, the same shape P1's
/// `AuthController` already uses for its writes.
class RecordListState {
  const RecordListState({
    this.items = const [],
    this.query = const RecordQuery(),
    this.isLoading = false,
    this.isLoadingMore = false,
    this.hasMore = false,
    this.error,
  });

  final List<PageRecord> items;
  final RecordQuery query;
  final bool isLoading;
  final bool isLoadingMore;
  final bool hasMore;
  final ApiException? error;

  RecordListState copyWith({
    List<PageRecord>? items,
    RecordQuery? query,
    bool? isLoading,
    bool? isLoadingMore,
    bool? hasMore,
    ApiException? error,
    bool clearError = false,
  }) {
    return RecordListState(
      items: items ?? this.items,
      query: query ?? this.query,
      isLoading: isLoading ?? this.isLoading,
      isLoadingMore: isLoadingMore ?? this.isLoadingMore,
      hasMore: hasMore ?? this.hasMore,
      error: clearError ? null : (error ?? this.error),
    );
  }
}

class RecordListController extends StateNotifier<RecordListState> {
  RecordListController(this._repository, this.pageId) : super(const RecordListState()) {
    _load(reset: true);
  }

  final PageRepository _repository;
  final String pageId;

  Future<void> _load({required bool reset}) async {
    if (reset) {
      state = state.copyWith(isLoading: true, clearError: true);
    } else {
      state = state.copyWith(isLoadingMore: true, clearError: true);
    }

    final query = reset ? state.query.copyWith(clearCursor: true) : state.query;
    try {
      final page = await _repository.queryRecords(pageId, query);
      state = state.copyWith(
        items: reset ? page.items : [...state.items, ...page.items],
        query: query.copyWith(cursor: page.nextCursor, clearCursor: page.nextCursor == null),
        hasMore: page.hasMore,
        isLoading: false,
        isLoadingMore: false,
      );
    } on ApiException catch (e) {
      state = state.copyWith(isLoading: false, isLoadingMore: false, error: e);
    }
  }

  /// Fetch the next page of the current query and append it.
  Future<void> loadMore() async {
    if (!state.hasMore || state.isLoading || state.isLoadingMore) return;
    await _load(reset: false);
  }

  /// Replace the filter/sort/search and start over from the first page.
  Future<void> applyQuery({
    List<RecordFilter>? filters,
    List<SortSpec>? sort,
    String? search,
    bool clearSearch = false,
  }) async {
    state = state.copyWith(
      query: state.query.copyWith(
        filters: filters,
        sort: sort,
        search: search,
        clearSearch: clearSearch,
        clearCursor: true,
      ),
    );
    await _load(reset: true);
  }

  /// Reload the first page with the query unchanged — after a create/edit
  /// elsewhere, or a pull-to-refresh.
  Future<void> refresh() => _load(reset: true);
}

final recordListControllerProvider =
    StateNotifierProvider.family<RecordListController, RecordListState, String>((ref, pageId) {
      return RecordListController(ref.watch(pageRepositoryProvider), pageId);
    });
