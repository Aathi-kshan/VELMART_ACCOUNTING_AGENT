/// CSV import (plan section 13.1, P3.5 Part 3) — mirrors
/// `app/schemas/csv_import.py`. Owner only, one generic pipeline for any
/// page: preview -> validate -> commit -> optional rollback within 24
/// hours.
library;

/// `POST /pages/{id}/import/preview`'s response — encoding/delimiter
/// detection, a fuzzy-suggested header -> column-key mapping, and a few
/// sample rows so the Owner can sanity-check the mapping before confirming
/// it.
class ImportPreview {
  const ImportPreview({
    required this.encoding,
    required this.delimiter,
    required this.headers,
    required this.suggestedMapping,
    required this.rowCount,
    required this.sampleRows,
  });

  factory ImportPreview.fromJson(Map<String, dynamic> json) {
    final rawMapping = (json['suggested_mapping'] as Map<String, dynamic>? ?? const {});
    return ImportPreview(
      encoding: json['encoding'] as String,
      delimiter: json['delimiter'] as String,
      headers: (json['headers'] as List<dynamic>).cast<String>(),
      suggestedMapping: rawMapping.map((k, v) => MapEntry(k, v as String?)),
      rowCount: json['row_count'] as int,
      sampleRows: (json['sample_rows'] as List<dynamic>)
          .cast<Map<String, dynamic>>()
          .map((row) => row.map((k, v) => MapEntry(k, v as String)))
          .toList(),
    );
  }

  final String encoding;
  final String delimiter;
  final List<String> headers;
  final Map<String, String?> suggestedMapping;
  final int rowCount;
  final List<Map<String, String>> sampleRows;
}

class ImportRowError {
  const ImportRowError({required this.row, this.column, required this.message});

  factory ImportRowError.fromJson(Map<String, dynamic> json) => ImportRowError(
    row: json['row'] as int,
    column: json['column'] as String?,
    message: json['message'] as String,
  );

  final int row;
  final String? column;
  final String message;
}

class ImportValidation {
  const ImportValidation({
    required this.totalRows,
    required this.validRows,
    required this.duplicateRows,
    required this.errorRows,
    required this.errors,
    required this.errorsTruncated,
  });

  factory ImportValidation.fromJson(Map<String, dynamic> json) => ImportValidation(
    totalRows: json['total_rows'] as int,
    validRows: json['valid_rows'] as int,
    duplicateRows: json['duplicate_rows'] as int,
    errorRows: json['error_rows'] as int,
    errors: (json['errors'] as List<dynamic>)
        .cast<Map<String, dynamic>>()
        .map(ImportRowError.fromJson)
        .toList(),
    errorsTruncated: json['errors_truncated'] as bool,
  );

  final int totalRows;
  final int validRows;
  final int duplicateRows;
  final int errorRows;
  final List<ImportRowError> errors;
  final bool errorsTruncated;
}

class ImportCommitResult {
  const ImportCommitResult({
    required this.batchId,
    required this.totalRows,
    required this.importedRows,
    required this.skippedRows,
    required this.errorRows,
  });

  factory ImportCommitResult.fromJson(Map<String, dynamic> json) => ImportCommitResult(
    batchId: json['batch_id'] as String,
    totalRows: json['total_rows'] as int,
    importedRows: json['imported_rows'] as int,
    skippedRows: json['skipped_rows'] as int,
    errorRows: json['error_rows'] as int,
  );

  final String batchId;
  final int totalRows;
  final int importedRows;
  final int skippedRows;
  final int errorRows;
}

/// How a row matching an existing natural key is handled (plan section
/// 13.1: "skip / update / create-anyway").
enum DuplicateStrategy {
  skip,
  update,
  createAnyway;

  String get wire => switch (this) {
    DuplicateStrategy.skip => 'skip',
    DuplicateStrategy.update => 'update',
    DuplicateStrategy.createAnyway => 'create_anyway',
  };

  String get label => switch (this) {
    DuplicateStrategy.skip => 'Skip duplicates',
    DuplicateStrategy.update => 'Update the existing record',
    DuplicateStrategy.createAnyway => 'Create a new record anyway',
  };
}

/// How to read an ambiguous (slash-separated) date column — set once per
/// column, never guessed (plan section 13.1).
enum DateFormatHint {
  ymd,
  dmy,
  mdy;

  String get wire => switch (this) {
    DateFormatHint.ymd => 'YMD',
    DateFormatHint.dmy => 'DMY',
    DateFormatHint.mdy => 'MDY',
  };

  String get label => switch (this) {
    DateFormatHint.ymd => 'Year / Month / Day',
    DateFormatHint.dmy => 'Day / Month / Year',
    DateFormatHint.mdy => 'Month / Day / Year',
  };
}

/// The Owner's confirmed choices for `/validate` and `/commit` — both take
/// exactly this shape (`ImportMappingRequest` server-side).
class ImportMapping {
  const ImportMapping({
    this.mapping = const {},
    this.naturalKeyColumns = const [],
    this.duplicateStrategy = DuplicateStrategy.createAnyway,
    this.dateFormats = const {},
  });

  final Map<String, String> mapping;
  final List<String> naturalKeyColumns;
  final DuplicateStrategy duplicateStrategy;
  final Map<String, DateFormatHint> dateFormats;

  ImportMapping copyWith({
    Map<String, String>? mapping,
    List<String>? naturalKeyColumns,
    DuplicateStrategy? duplicateStrategy,
    Map<String, DateFormatHint>? dateFormats,
  }) => ImportMapping(
    mapping: mapping ?? this.mapping,
    naturalKeyColumns: naturalKeyColumns ?? this.naturalKeyColumns,
    duplicateStrategy: duplicateStrategy ?? this.duplicateStrategy,
    dateFormats: dateFormats ?? this.dateFormats,
  );

  Map<String, dynamic> toJson() => {
    'mapping': mapping,
    'natural_key_columns': naturalKeyColumns,
    'duplicate_strategy': duplicateStrategy.wire,
    'date_formats': dateFormats.map((key, hint) => MapEntry(key, hint.wire)),
  };
}

class ImportBatch {
  const ImportBatch({
    required this.id,
    required this.pageId,
    required this.fileName,
    required this.totalRows,
    required this.importedRows,
    required this.skippedRows,
    required this.status,
    required this.createdAt,
    required this.canRollback,
  });

  factory ImportBatch.fromJson(Map<String, dynamic> json) => ImportBatch(
    id: json['id'] as String,
    pageId: json['page_id'] as String,
    fileName: json['file_name'] as String,
    totalRows: json['total_rows'] as int,
    importedRows: json['imported_rows'] as int,
    skippedRows: json['skipped_rows'] as int,
    status: json['status'] as String,
    createdAt: json['created_at'] as String,
    canRollback: json['can_rollback'] as bool,
  );

  final String id;
  final String pageId;
  final String fileName;
  final int totalRows;
  final int importedRows;
  final int skippedRows;
  final String status;
  final String createdAt;
  final bool canRollback;
}
