import 'column.dart';

/// An Owner-defined page — one table the Owner invented (plan section 10.1).
///
/// Mirrors `PageOut` / `PageSchemaOut` in `app/schemas/page.py`. `key` is the
/// server-derived slug; `is_system` marks the six shipped business pages,
/// whose schema changes by migration rather than through the API
/// (docs/API.md section 1.7).
class Page {
  const Page({
    required this.id,
    required this.companyId,
    required this.key,
    required this.name,
    required this.kind,
    required this.isArchived,
    required this.isSystem,
    required this.version,
    this.description,
    this.icon,
    this.dateColumnKey,
    this.storeColumnKey,
    this.storageTable,
  });

  factory Page.fromJson(Map<String, dynamic> json) {
    return Page(
      id: json['id'] as String,
      companyId: json['company_id'] as String,
      key: json['key'] as String,
      name: json['name'] as String,
      kind: PageKind.fromWire(json['kind'] as String),
      description: json['description'] as String?,
      icon: json['icon'] as String?,
      dateColumnKey: json['date_column_key'] as String?,
      storeColumnKey: json['store_column_key'] as String?,
      isArchived: json['is_archived'] as bool,
      isSystem: json['is_system'] as bool,
      storageTable: json['storage_table'] as String?,
      version: json['version'] as int,
    );
  }

  final String id;
  final String companyId;
  final String key;
  final String name;
  final PageKind kind;
  final String? description;
  final String? icon;

  /// Which column drives `business_date`, if any (plan section 9.2).
  final String? dateColumnKey;

  /// Which column drives store scoping, if any (plan section 4.5).
  final String? storeColumnKey;

  final bool isArchived;

  /// True for the six shipped business pages. Their columns cannot be edited
  /// (409 `SYSTEM_PAGE_IMMUTABLE`), so the client hides the column editor.
  final bool isSystem;

  /// The native table a system page's rows live in, instead of `records`.
  final String? storageTable;

  final int version;
}

/// How corrections work on a page (plan section 10.1).
enum PageKind {
  /// The Owner edits rows in place.
  register,

  /// Rows are corrected by a reversal record, never edited. The reversal
  /// mechanics themselves arrive with P4.
  ledger;

  static PageKind fromWire(String value) => switch (value) {
    'REGISTER' => PageKind.register,
    'LEDGER' => PageKind.ledger,
    _ => throw ArgumentError('Unknown page kind: $value'),
  };

  String get wire => this == PageKind.register ? 'REGISTER' : 'LEDGER';

  String get label => this == PageKind.register ? 'Register' : 'Ledger';
}

/// A page plus its columns — the shape `GET /pages/{id}/schema` returns, and
/// everything the dynamic form and table need to render themselves.
class PageSchema {
  const PageSchema({
    required this.page,
    required this.columns,
    this.generatedColumns = const {},
  });

  factory PageSchema.fromJson(Map<String, dynamic> json) {
    final columns = (json['columns'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map(PageColumn.fromJson)
        .toList()
      ..sort((a, b) => a.position.compareTo(b.position));

    final generatedColumns = (json['generated_columns'] as List<dynamic>? ?? const [])
        .cast<String>()
        .toSet();

    return PageSchema(
      page: Page.fromJson(json),
      columns: columns,
      generatedColumns: generatedColumns,
    );
  }

  final Page page;

  /// Active columns in display order. The server already filters archived
  /// ones out of the schema response.
  final List<PageColumn> columns;

  /// Column keys that are DB-computed on this page's storage table (e.g.
  /// `daily_revenue.total_revenue`) — always empty for a generic page.
  /// Rendered read-only, same as `FORMULA`, but by key rather than by
  /// `ColumnType` since these are ordinary `CURRENCY` columns that just
  /// happen to be server-computed on the six system pages.
  final Set<String> generatedColumns;

  /// Columns a person can type into through the generic record form —
  /// everything except FORMULA/ATTACHMENT (see `ColumnType.isReadOnly`),
  /// this page's own generated columns, and protected columns (P4: no one
  /// changes a protected value through this generic path any more, only
  /// through the dedicated protected-field action — see
  /// `record_detail_screen.dart`).
  List<PageColumn> get writableColumns => columns
      .where(
        (c) => !c.dataType.isReadOnly && !generatedColumns.contains(c.key) && !c.isProtected,
      )
      .toList();

  PageColumn? columnByKey(String key) {
    for (final column in columns) {
      if (column.key == key) return column;
    }
    return null;
  }

  /// The column to headline a record with in a list or a reference picker:
  /// the first text-ish column, falling back to the first column at all.
  PageColumn? get displayColumn {
    for (final column in columns) {
      if (column.dataType == ColumnType.text) return column;
    }
    return columns.isEmpty ? null : columns.first;
  }
}

/// One row of `PUT /pages/{id}/access` (plan section 3.10, docs/API.md
/// section 4). Grants are replaced wholesale — there is no per-grant PATCH.
class AccessGrant {
  const AccessGrant({
    required this.userId,
    this.canView = true,
    this.canCreate = true,
    this.userName,
  });

  factory AccessGrant.fromJson(Map<String, dynamic> json) => AccessGrant(
    userId: json['user_id'] as String,
    canView: json['can_view'] as bool? ?? true,
    canCreate: json['can_create'] as bool? ?? true,
  );

  final String userId;
  final bool canView;
  final bool canCreate;

  /// Filled in client-side from `/users` for display — never sent.
  final String? userName;

  Map<String, dynamic> toJson() => {
    'user_id': userId,
    'can_view': canView,
    'can_create': canCreate,
  };

  AccessGrant copyWith({bool? canView, bool? canCreate}) => AccessGrant(
    userId: userId,
    canView: canView ?? this.canView,
    canCreate: canCreate ?? this.canCreate,
    userName: userName,
  );
}
