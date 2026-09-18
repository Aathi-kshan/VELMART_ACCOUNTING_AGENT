import 'column.dart';

/// One row of an Owner-defined page (plan section 8.3).
///
/// Named `PageRecord`, not `Record` — `Record` is a built-in Dart 3 type.
///
/// Mirrors `RecordOut` in `app/schemas/record.py`. `data` holds the Owner's
/// own columns keyed by column `key`, already in **wire format**: money and
/// numbers as strings, dates as ISO text, booleans as real booleans (plan
/// section 9.1). Nothing here converts them — `AmountText` and the field
/// renderers do that at the edge where they are displayed or edited.
class PageRecord {
  const PageRecord({
    required this.id,
    required this.companyId,
    required this.pageId,
    required this.occurredAt,
    required this.businessDate,
    required this.status,
    required this.data,
    required this.needsReview,
    required this.version,
    required this.createdBy,
    this.storeId,
    this.updatedBy,
  });

  factory PageRecord.fromJson(Map<String, dynamic> json) {
    return PageRecord(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      pageId: json['page_id'] as String,
      storeId: json['store_id'] as String?,
      occurredAt: json['occurred_at'] as String,
      businessDate: json['business_date'] as String,
      status: RecordStatus.fromWire(json['status'] as String),
      data: (json['data'] as Map<String, dynamic>? ?? const {}),
      needsReview: json['needs_review'] as bool,
      version: json['version'] as int,
      createdBy: json['created_by'] as String,
      updatedBy: json['updated_by'] as String?,
    );
  }

  final String id;
  final String companyId;
  final String pageId;
  final String? storeId;

  /// When the business event happened — ISO 8601 with offset.
  final String occurredAt;

  /// The accounting day, derived server-side (plan section 9.2). Read-only.
  final String businessDate;

  final RecordStatus status;

  /// The Owner's columns, keyed by column `key`, in wire format.
  final Map<String, dynamic> data;

  /// Set by a WARNING validation rule (plan section 11.3). Rules themselves
  /// arrive with P4; the flag is displayed here when the server sets it.
  final bool needsReview;

  /// Optimistic-locking version — sent back as `If-Match` on edit.
  final int version;

  final String createdBy;
  final String? updatedBy;

  /// The stored value for a column, or null.
  Object? valueFor(PageColumn column) => data[column.key];
}

/// The platform record lifecycle (plan section 4.4) — distinct from any
/// Owner-defined status column, which is why `cheques` names its own one
/// `cheque_status` (docs/API.md section 1.7).
enum RecordStatus {
  active,
  reversed,
  void_;

  static RecordStatus fromWire(String value) => switch (value) {
    'ACTIVE' => RecordStatus.active,
    'REVERSED' => RecordStatus.reversed,
    'VOID' => RecordStatus.void_,
    _ => throw ArgumentError('Unknown record status: $value'),
  };

  String get label => switch (this) {
    RecordStatus.active => 'Active',
    RecordStatus.reversed => 'Reversed',
    RecordStatus.void_ => 'Void',
  };

  String get wire => switch (this) {
    RecordStatus.active => 'ACTIVE',
    RecordStatus.reversed => 'REVERSED',
    RecordStatus.void_ => 'VOID',
  };
}

// --------------------------------------------------------------------------
// Query language (plan section 10.4)
// --------------------------------------------------------------------------

/// The structured filter operators the server accepts. Column keys are
/// validated against `page_columns` server-side and mapped to safe
/// expressions — never interpolated into SQL (plan section 3.8).
enum FilterOp {
  eq,
  neq,
  gt,
  gte,
  lt,
  lte,
  between,
  inList,
  contains,
  isNull;

  String get wire => switch (this) {
    FilterOp.eq => 'eq',
    FilterOp.neq => 'neq',
    FilterOp.gt => 'gt',
    FilterOp.gte => 'gte',
    FilterOp.lt => 'lt',
    FilterOp.lte => 'lte',
    FilterOp.between => 'between',
    FilterOp.inList => 'in',
    FilterOp.contains => 'contains',
    FilterOp.isNull => 'is_null',
  };

  String get label => switch (this) {
    FilterOp.eq => 'is',
    FilterOp.neq => 'is not',
    FilterOp.gt => 'more than',
    FilterOp.gte => 'at least',
    FilterOp.lt => 'less than',
    FilterOp.lte => 'at most',
    FilterOp.between => 'between',
    FilterOp.inList => 'is one of',
    FilterOp.contains => 'contains',
    FilterOp.isNull => 'is empty',
  };

  /// Which operators make sense for a column type. Offering "more than" on a
  /// yes/no column is how a filter sheet becomes confusing.
  static List<FilterOp> forType(ColumnType type) => switch (type) {
    ColumnType.text || ColumnType.longText => const [
      FilterOp.eq,
      FilterOp.neq,
      FilterOp.contains,
      FilterOp.isNull,
    ],
    ColumnType.number || ColumnType.currency || ColumnType.percent => const [
      FilterOp.eq,
      FilterOp.neq,
      FilterOp.gt,
      FilterOp.gte,
      FilterOp.lt,
      FilterOp.lte,
      FilterOp.between,
      FilterOp.isNull,
    ],
    ColumnType.date || ColumnType.datetime => const [
      FilterOp.eq,
      FilterOp.gte,
      FilterOp.lte,
      FilterOp.between,
      FilterOp.isNull,
    ],
    ColumnType.boolean => const [FilterOp.eq, FilterOp.isNull],
    ColumnType.select || ColumnType.multiSelect => const [
      FilterOp.eq,
      FilterOp.neq,
      FilterOp.inList,
      FilterOp.isNull,
    ],
    ColumnType.recordRef || ColumnType.storeRef || ColumnType.userRef => const [
      FilterOp.eq,
      FilterOp.neq,
      FilterOp.isNull,
    ],
    // Not filterable in P3: FORMULA has no stored value until P4's evaluator,
    // and ATTACHMENT holds a count the attachment endpoints (P5) maintain.
    ColumnType.formula || ColumnType.attachment => const [],
  };
}

class RecordFilter {
  const RecordFilter({required this.column, required this.op, this.value});

  final String column;
  final FilterOp op;

  /// A scalar, a 2-element list for `between`, a list for `in`, or null for
  /// `is_null`. Always in wire format.
  final Object? value;

  Map<String, dynamic> toJson() => {
    'column': column,
    'op': op.wire,
    'value': value,
  };
}

class SortSpec {
  const SortSpec({required this.column, this.descending = false});

  final String column;
  final bool descending;

  Map<String, dynamic> toJson() => {
    'column': column,
    'direction': descending ? 'desc' : 'asc',
  };
}

/// The body of `POST /pages/{id}/records/query`.
class RecordQuery {
  const RecordQuery({
    this.filters = const [],
    this.sort = const [],
    this.search,
    this.cursor,
    this.limit = 50,
  });

  final List<RecordFilter> filters;
  final List<SortSpec> sort;
  final String? search;
  final String? cursor;
  final int limit;

  RecordQuery copyWith({
    List<RecordFilter>? filters,
    List<SortSpec>? sort,
    String? search,
    String? cursor,
    int? limit,
    bool clearCursor = false,
    bool clearSearch = false,
  }) {
    return RecordQuery(
      filters: filters ?? this.filters,
      sort: sort ?? this.sort,
      search: clearSearch ? null : (search ?? this.search),
      cursor: clearCursor ? null : (cursor ?? this.cursor),
      limit: limit ?? this.limit,
    );
  }

  Map<String, dynamic> toJson() => {
    'filters': filters.map((f) => f.toJson()).toList(),
    'sort': sort.map((s) => s.toJson()).toList(),
    if (search != null && search!.isNotEmpty) 'search': search,
    if (cursor != null) 'cursor': cursor,
    'limit': limit,
  };

  /// Two queries describe the same result set when everything but the cursor
  /// matches — used to know when to reset pagination rather than append.
  bool sameShapeAs(RecordQuery other) {
    if (search != other.search || limit != other.limit) return false;
    if (filters.length != other.filters.length) return false;
    if (sort.length != other.sort.length) return false;
    for (var i = 0; i < filters.length; i++) {
      final a = filters[i];
      final b = other.filters[i];
      if (a.column != b.column || a.op != b.op || '${a.value}' != '${b.value}') {
        return false;
      }
    }
    for (var i = 0; i < sort.length; i++) {
      if (sort[i].column != other.sort[i].column ||
          sort[i].descending != other.sort[i].descending) {
        return false;
      }
    }
    return true;
  }
}

/// `sum, avg, count, min, max` (plan section 10.4), executed in Postgres —
/// the client never sums a column itself.
enum AggregateMetric {
  sum,
  avg,
  count,
  min,
  max;

  String get wire => name;
}

/// The body of `POST /pages/{id}/aggregate`.
class AggregateQuery {
  const AggregateQuery({
    required this.metric,
    this.column,
    this.groupBy,
    this.period = 'all_time',
    this.filters = const [],
  });

  final AggregateMetric metric;
  final String? column;
  final String? groupBy;

  /// `current_month` · `last_month` · `current_year` · `all_time`.
  final String period;
  final List<RecordFilter> filters;

  Map<String, dynamic> toJson() => {
    'metric': metric.wire,
    if (column != null) 'column': column,
    if (groupBy != null) 'group_by': groupBy,
    'period': period,
    'filters': filters.map((f) => f.toJson()).toList(),
  };
}

class AggregateGroup {
  const AggregateGroup({required this.key, required this.value, required this.count});

  factory AggregateGroup.fromJson(Map<String, dynamic> json) => AggregateGroup(
    key: json['key'] as String,
    value: json['value'] as String,
    count: json['count'] as int,
  );

  final String key;

  /// Always a wire-format string (money stays a string all the way through).
  final String value;
  final int count;
}

class AggregateResult {
  const AggregateResult({
    required this.value,
    required this.recordCount,
    required this.groups,
  });

  factory AggregateResult.fromJson(Map<String, dynamic> json) => AggregateResult(
    value: json['value'] as String,
    recordCount: json['record_count'] as int,
    groups: (json['groups'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(AggregateGroup.fromJson)
        .toList(),
  );

  final String value;
  final int recordCount;
  final List<AggregateGroup> groups;
}

/// The cursor-paginated envelope every list endpoint returns (docs/API.md
/// section 1.3).
class Paginated<T> {
  const Paginated({required this.items, this.nextCursor, this.hasMore = false});

  factory Paginated.fromJson(
    Map<String, dynamic> json,
    T Function(Map<String, dynamic>) parseItem,
  ) {
    return Paginated(
      items: (json['items'] as List<dynamic>? ?? const [])
          .cast<Map<String, dynamic>>()
          .map(parseItem)
          .toList(),
      nextCursor: json['next_cursor'] as String?,
      hasMore: json['has_more'] as bool? ?? false,
    );
  }

  final List<T> items;
  final String? nextCursor;
  final bool hasMore;
}
