/// One column of an Owner-defined page (plan sections 8.3, 10.2).
///
/// Mirrors `ColumnOut` in `app/schemas/column.py`. `key` is the stable slug
/// the server derived from `name` and is immutable for the column's life —
/// renaming changes `name` only (plan section 10.3), so everything that
/// stores or filters a value keys on `key`, never on `name`.
library;

/// The 15 column types (plan section 10.2). This list is closed: a new kind
/// of data is a new type here *and* in `app/models/page_column.py`.
enum ColumnType {
  text,
  longText,
  number,
  currency,
  percent,
  date,
  datetime,
  boolean,
  select,
  multiSelect,
  recordRef,
  storeRef,
  userRef,
  formula,
  attachment;

  /// Enums cannot declare factory constructors in Dart, so this is a static
  /// method — matching `UserRole.fromWire` in features/auth/domain/user.dart.
  static ColumnType fromWire(String value) => switch (value) {
    'TEXT' => ColumnType.text,
    'LONG_TEXT' => ColumnType.longText,
    'NUMBER' => ColumnType.number,
    'CURRENCY' => ColumnType.currency,
    'PERCENT' => ColumnType.percent,
    'DATE' => ColumnType.date,
    'DATETIME' => ColumnType.datetime,
    'BOOLEAN' => ColumnType.boolean,
    'SELECT' => ColumnType.select,
    'MULTI_SELECT' => ColumnType.multiSelect,
    'RECORD_REF' => ColumnType.recordRef,
    'STORE_REF' => ColumnType.storeRef,
    'USER_REF' => ColumnType.userRef,
    'FORMULA' => ColumnType.formula,
    'ATTACHMENT' => ColumnType.attachment,
    _ => throw ArgumentError('Unknown column type: $value'),
  };

  /// The wire value the API expects when defining or filtering a column.
  String get wire => switch (this) {
    ColumnType.text => 'TEXT',
    ColumnType.longText => 'LONG_TEXT',
    ColumnType.number => 'NUMBER',
    ColumnType.currency => 'CURRENCY',
    ColumnType.percent => 'PERCENT',
    ColumnType.date => 'DATE',
    ColumnType.datetime => 'DATETIME',
    ColumnType.boolean => 'BOOLEAN',
    ColumnType.select => 'SELECT',
    ColumnType.multiSelect => 'MULTI_SELECT',
    ColumnType.recordRef => 'RECORD_REF',
    ColumnType.storeRef => 'STORE_REF',
    ColumnType.userRef => 'USER_REF',
    ColumnType.formula => 'FORMULA',
    ColumnType.attachment => 'ATTACHMENT',
  };

  /// What the Owner sees when picking a type in the page builder.
  String get label => switch (this) {
    ColumnType.text => 'Text',
    ColumnType.longText => 'Long text',
    ColumnType.number => 'Number',
    ColumnType.currency => 'Money',
    ColumnType.percent => 'Percentage',
    ColumnType.date => 'Date',
    ColumnType.datetime => 'Date and time',
    ColumnType.boolean => 'Yes / no',
    ColumnType.select => 'Choice',
    ColumnType.multiSelect => 'Multiple choice',
    ColumnType.recordRef => 'Link to another page',
    ColumnType.storeRef => 'Store',
    ColumnType.userRef => 'Person',
    ColumnType.formula => 'Formula',
    ColumnType.attachment => 'Attachment',
  };

  /// Types the server can index into a projection column, and so sort and
  /// filter without scanning JSONB (plan section 3.3). Only 4 numeric and 2
  /// date slots exist per page — the server returns 409 past that.
  bool get isIndexable => switch (this) {
    ColumnType.number ||
    ColumnType.currency ||
    ColumnType.date ||
    ColumnType.datetime => true,
    _ => false,
  };

  /// Types the Owner cannot write a value into. FORMULA is computed on read
  /// (plan section 11.1); ATTACHMENT holds a count maintained by the
  /// attachment endpoints (plan section 10.2), which arrive in P5.
  bool get isReadOnly => this == ColumnType.formula || this == ColumnType.attachment;

  /// Only a SELECT can be marked protected (plan section 11.4).
  bool get supportsProtection => this == ColumnType.select;

  /// Types an Owner may pick when defining a new column.
  ///
  /// Excludes ATTACHMENT. The type parses, renders and round-trips — but the
  /// attachment endpoints were deferred and `app/routers/attachments.py` is
  /// not mounted, so a column created with it shows "Uploading attachments is
  /// coming soon" permanently and can never hold anything. Offering a choice
  /// that cannot work is worse than not offering it; the value stays in the
  /// enum so any column already carrying it still parses and displays.
  static List<ColumnType> get selectableForNewColumn =>
      ColumnType.values.where((t) => t != ColumnType.attachment).toList();

  /// Types whose `config` must carry an `options` list.
  bool get needsOptions => this == ColumnType.select || this == ColumnType.multiSelect;
}

class PageColumn {
  const PageColumn({
    required this.id,
    required this.pageId,
    required this.key,
    required this.name,
    required this.dataType,
    required this.position,
    required this.isRequired,
    required this.isIndexed,
    required this.isProtected,
    required this.config,
    required this.isArchived,
    this.description,
  });

  factory PageColumn.fromJson(Map<String, dynamic> json) {
    return PageColumn(
      id: json['id'] as String,
      pageId: json['page_id'] as String,
      key: json['key'] as String,
      name: json['name'] as String,
      dataType: ColumnType.fromWire(json['data_type'] as String),
      position: json['position'] as int,
      isRequired: json['is_required'] as bool,
      isIndexed: json['is_indexed'] as bool,
      isProtected: json['is_protected'] as bool,
      config: (json['config'] as Map<String, dynamic>? ?? const {}),
      description: json['description'] as String?,
      isArchived: json['is_archived'] as bool,
    );
  }

  final String id;
  final String pageId;
  final String key;
  final String name;
  final ColumnType dataType;
  final int position;
  final bool isRequired;
  final bool isIndexed;
  final bool isProtected;
  final Map<String, dynamic> config;
  final String? description;
  final bool isArchived;

  // --- typed `config` accessors (plan section 8.3) -------------------------

  /// SELECT / MULTI_SELECT allowed values.
  List<String> get options {
    final raw = config['options'];
    if (raw is! List) return const [];
    return raw.whereType<String>().toList();
  }

  /// The value a protected column takes when a manager creates a record, and
  /// the form's prefill otherwise (e.g. `PENDING`).
  Object? get defaultValue => config['default'];

  /// NUMBER / CURRENCY / PERCENT bounds, as wire strings so they never pass
  /// through a double.
  String? get minValue => _numberAsString(config['min']);
  String? get maxValue => _numberAsString(config['max']);

  bool get allowNegative => config['allow_negative'] == true;

  /// RECORD_REF: which page this points at, and which of its columns to show
  /// in the picker (plan section 11.2).
  String? get targetPageKey => config['target_page_key'] as String?;
  String? get displayColumn => config['display_column'] as String?;

  /// FORMULA: the Owner's expression. Opaque to the client — it is parsed and
  /// evaluated server-side, never here (plan section 11.1).
  String? get expression => config['expression'] as String?;

  static String? _numberAsString(Object? value) => switch (value) {
    null => null,
    final String s => s,
    final int i => i.toString(),
    final num n => n.toString(),
    _ => null,
  };
}

/// One column inside `POST /pages` or the body of `POST /pages/{id}/columns`
/// (mirrors `ColumnDefinition` in `app/schemas/column.py`). `key` is never
/// sent — it's always derived server-side from `name`.
class ColumnDefinition {
  const ColumnDefinition({
    required this.name,
    required this.dataType,
    this.isRequired = false,
    this.isIndexed = false,
    this.isProtected = false,
    this.config = const {},
    this.description,
  });

  final String name;
  final ColumnType dataType;
  final bool isRequired;
  final bool isIndexed;
  final bool isProtected;
  final Map<String, dynamic> config;
  final String? description;

  Map<String, dynamic> toJson() => {
    'name': name,
    'data_type': dataType.wire,
    'is_required': isRequired,
    'is_indexed': isIndexed,
    'is_protected': isProtected,
    'config': config,
    if (description != null) 'description': description,
  };
}

/// The response to `POST /columns/{id}/narrow-dry-run` — informational only,
/// never mutates anything (plan section 10.3).
class NarrowDryRunResult {
  const NarrowDryRunResult({required this.wouldFail, required this.sampleFailures});

  factory NarrowDryRunResult.fromJson(Map<String, dynamic> json) => NarrowDryRunResult(
    wouldFail: json['would_fail'] as int,
    sampleFailures: (json['sample_failures'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>(),
  );

  final int wouldFail;
  final List<Map<String, dynamic>> sampleFailures;
}

/// The result of `PATCH /columns/{id}`: the updated column, plus any
/// SELECT/MULTI_SELECT options removed while still in use (a warning, not a
/// block — plan section 10.3).
class UpdateColumnResult {
  const UpdateColumnResult({required this.column, required this.removedOptionsInUse});

  factory UpdateColumnResult.fromJson(Map<String, dynamic> json) => UpdateColumnResult(
    column: PageColumn.fromJson(json),
    removedOptionsInUse: (json['removed_options_in_use'] as Map<String, dynamic>? ?? const {})
        .map((key, value) => MapEntry(key, value as int)),
  );

  final PageColumn column;
  final Map<String, int> removedOptionsInUse;
}
