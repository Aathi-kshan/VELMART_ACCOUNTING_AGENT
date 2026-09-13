import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import '../../../core/network/api_exception.dart';
import '../../auth/domain/user.dart';
import '../domain/column.dart';
import '../domain/csv_import.dart';
import '../domain/page.dart';
import '../domain/record.dart';
import '../domain/store.dart';
import '../domain/validation_rule.dart';

/// Every endpoint P3's backend exposes, one method each (plan sections
/// 3.10-3.11, 21.2). Thin by design: this repository does no validation and
/// makes no decisions of its own — it sends what it's given and parses what
/// comes back, exactly like `AuthRepository`. Every call is wrapped in
/// [mapApiErrors] so screens only ever catch [ApiException].
class PageRepository {
  PageRepository({required this.dio});

  final Dio dio;
  final _uuid = const Uuid();

  // --- pages ----------------------------------------------------------

  Future<List<Page>> listPages() => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/pages');
    return response.data!.cast<Map<String, dynamic>>().map(Page.fromJson).toList();
  });

  Future<PageSchema> getSchema(String pageId) => mapApiErrors(() async {
    final response = await dio.get<Map<String, dynamic>>('/pages/$pageId/schema');
    return PageSchema.fromJson(response.data!);
  });

  Future<PageSchema> createPage({
    required String name,
    PageKind kind = PageKind.register,
    String? description,
    String? icon,
    List<ColumnDefinition> columns = const [],
    String? dateColumnKey,
    String? storeColumnKey,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/pages',
      data: {
        'name': name,
        'kind': kind.wire,
        if (description != null) 'description': description,
        if (icon != null) 'icon': icon,
        'columns': columns.map((c) => c.toJson()).toList(),
        if (dateColumnKey != null) 'date_column_key': dateColumnKey,
        if (storeColumnKey != null) 'store_column_key': storeColumnKey,
      },
    );
    return PageSchema.fromJson(response.data!);
  });

  Future<PageSchema> updatePage(
    String pageId, {
    String? name,
    String? description,
    String? icon,
    String? dateColumnKey,
    String? storeColumnKey,
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/pages/$pageId',
      data: {
        if (name != null) 'name': name,
        if (description != null) 'description': description,
        if (icon != null) 'icon': icon,
        if (dateColumnKey != null) 'date_column_key': dateColumnKey,
        if (storeColumnKey != null) 'store_column_key': storeColumnKey,
      },
    );
    return PageSchema.fromJson(response.data!);
  });

  Future<Page> archivePage(String pageId) => mapApiErrors(() async {
    final response = await dio.delete<Map<String, dynamic>>('/pages/$pageId');
    return Page.fromJson(response.data!);
  });

  // --- columns ----------------------------------------------------------

  Future<PageColumn> addColumn(String pageId, ColumnDefinition definition) =>
      mapApiErrors(() async {
        final response = await dio.post<Map<String, dynamic>>(
          '/pages/$pageId/columns',
          data: definition.toJson(),
        );
        return PageColumn.fromJson(response.data!);
      });

  Future<UpdateColumnResult> updateColumn(
    String columnId, {
    String? name,
    ColumnType? dataType,
    bool confirmNarrow = false,
    int? position,
    bool? isRequired,
    bool? isIndexed,
    bool? isProtected,
    Map<String, dynamic>? config,
    String? description,
    bool? isArchived,
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/columns/$columnId',
      data: {
        if (name != null) 'name': name,
        if (dataType != null) 'data_type': dataType.wire,
        'confirm_narrow': confirmNarrow,
        if (position != null) 'position': position,
        if (isRequired != null) 'is_required': isRequired,
        if (isIndexed != null) 'is_indexed': isIndexed,
        if (isProtected != null) 'is_protected': isProtected,
        if (config != null) 'config': config,
        if (description != null) 'description': description,
        if (isArchived != null) 'is_archived': isArchived,
      },
    );
    return UpdateColumnResult.fromJson(response.data!);
  });

  Future<PageColumn> archiveColumn(String columnId) => mapApiErrors(() async {
    final response = await dio.delete<Map<String, dynamic>>('/columns/$columnId');
    return PageColumn.fromJson(response.data!);
  });

  Future<NarrowDryRunResult> narrowDryRun(String columnId, ColumnType proposedType) =>
      mapApiErrors(() async {
        final response = await dio.post<Map<String, dynamic>>(
          '/columns/$columnId/narrow-dry-run',
          data: {'data_type': proposedType.wire},
        );
        return NarrowDryRunResult.fromJson(response.data!);
      });

  // --- access -------------------------------------------------------------

  Future<List<AccessGrant>> setAccess(String pageId, List<AccessGrant> grants) =>
      mapApiErrors(() async {
        final response = await dio.put<List<dynamic>>(
          '/pages/$pageId/access',
          data: {'grants': grants.map((g) => g.toJson()).toList()},
        );
        return response.data!.cast<Map<String, dynamic>>().map(AccessGrant.fromJson).toList();
      });

  // --- page_validations (P4 §6) ---------------------------------------

  Future<ValidationRule> createValidation(
    String pageId, {
    required String name,
    required String expression,
    required ValidationSeverity severity,
    required String message,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/pages/$pageId/validations',
      data: {
        'name': name,
        'expression': expression,
        'severity': severity.wire,
        'message': message,
      },
    );
    return ValidationRule.fromJson(response.data!);
  });

  Future<ValidationRule> updateValidation(
    String ruleId, {
    String? name,
    String? expression,
    ValidationSeverity? severity,
    String? message,
    bool? isActive,
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/validations/$ruleId',
      data: {
        if (name != null) 'name': name,
        if (expression != null) 'expression': expression,
        if (severity != null) 'severity': severity.wire,
        if (message != null) 'message': message,
        if (isActive != null) 'is_active': isActive,
      },
    );
    return ValidationRule.fromJson(response.data!);
  });

  Future<ValidationRule> archiveValidation(String ruleId) => mapApiErrors(() async {
    final response = await dio.delete<Map<String, dynamic>>('/validations/$ruleId');
    return ValidationRule.fromJson(response.data!);
  });

  // --- records --------------------------------------------------------

  Future<Paginated<PageRecord>> listRecords(
    String pageId, {
    String? cursor,
    int limit = 50,
  }) => mapApiErrors(() async {
    final response = await dio.get<Map<String, dynamic>>(
      '/pages/$pageId/records',
      queryParameters: {if (cursor != null) 'cursor': cursor, 'limit': limit},
    );
    return Paginated.fromJson(response.data!, PageRecord.fromJson);
  });

  Future<Paginated<PageRecord>> queryRecords(String pageId, RecordQuery query) =>
      mapApiErrors(() async {
        final response = await dio.post<Map<String, dynamic>>(
          '/pages/$pageId/records/query',
          data: query.toJson(),
        );
        return Paginated.fromJson(response.data!, PageRecord.fromJson);
      });

  Future<PageRecord> getRecord(String recordId) => mapApiErrors(() async {
    final response = await dio.get<Map<String, dynamic>>('/records/$recordId');
    return PageRecord.fromJson(response.data!);
  });

  /// `client_uuid` doubles as the `Idempotency-Key` (plan section 21.1) — the
  /// same value drains the offline outbox safely in P6, so it's generated
  /// once here rather than left to each call site.
  Future<PageRecord> createRecord(
    String pageId, {
    required String occurredAt,
    String? storeId,
    required Map<String, dynamic> data,
  }) => mapApiErrors(() async {
    final clientUuid = _uuid.v4();
    final response = await dio.post<Map<String, dynamic>>(
      '/pages/$pageId/records',
      data: {
        'occurred_at': occurredAt,
        'client_uuid': clientUuid,
        if (storeId != null) 'store_id': storeId,
        'data': data,
      },
      options: Options(headers: {'Idempotency-Key': clientUuid}),
    );
    return PageRecord.fromJson(response.data!);
  });

  /// `version` becomes the `If-Match` header — every mutable row is
  /// optimistically locked (docs/API.md section 1.2), and a stale value
  /// comes back as a 409 `VERSION_CONFLICT` carrying `current_version`.
  Future<PageRecord> updateRecord(
    String recordId, {
    required int version,
    String? occurredAt,
    String? storeId,
    Map<String, dynamic> data = const {},
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/records/$recordId',
      data: {
        if (occurredAt != null) 'occurred_at': occurredAt,
        if (storeId != null) 'store_id': storeId,
        'data': data,
      },
      options: Options(headers: {'If-Match': '$version'}),
    );
    return PageRecord.fromJson(response.data!);
  });

  Future<void> deleteRecord(String recordId, {required String reason}) =>
      mapApiErrors(() async {
        await dio.delete<void>('/records/$recordId', data: {'reason': reason});
      });

  /// The only way a protected column ever changes (plan section 11.4) —
  /// owner-only on the server. `version` becomes `If-Match`, same as
  /// [updateRecord].
  Future<PageRecord> setProtectedField(
    String recordId, {
    required String columnKey,
    required String value,
    required int version,
  }) => mapApiErrors(() async {
    final response = await dio.patch<Map<String, dynamic>>(
      '/records/$recordId/protected-field',
      data: {'column_key': columnKey, 'value': value},
      options: Options(headers: {'If-Match': '$version'}),
    );
    return PageRecord.fromJson(response.data!);
  });

  // --- query / aggregate / discovery ---------------------------------------

  Future<AggregateResult> aggregate(String pageId, AggregateQuery query) =>
      mapApiErrors(() async {
        final response = await dio.post<Map<String, dynamic>>(
          '/pages/$pageId/aggregate',
          data: query.toJson(),
        );
        return AggregateResult.fromJson(response.data!);
      });

  Future<List<String>> columnValues(String pageId, String columnKey) =>
      mapApiErrors(() async {
        final response = await dio.get<Map<String, dynamic>>(
          '/pages/$pageId/column-values/$columnKey',
        );
        return (response.data!['values'] as List<dynamic>).cast<String>();
      });

  // --- export -----------------------------------------------------------

  /// Owner-only on the server (403 for a manager). Reuses whatever
  /// filter/search a record list already has applied, so "export what I'm
  /// looking at" matches what actually gets written — same request shape
  /// as [queryRecords], minus `sort`/`cursor`/`limit` (an export has no
  /// pagination and doesn't need a client-chosen order).
  Future<Uint8List> exportCsv(
    String pageId, {
    List<RecordFilter> filters = const [],
    String? search,
  }) async {
    try {
      final response = await dio.post<List<int>>(
        '/pages/$pageId/export',
        data: {
          'filters': filters.map((f) => f.toJson()).toList(),
          if (search != null) 'search': search,
        },
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data!);
    } on DioException catch (error) {
      throw ApiException.fromDio(decodeBytesResponseError(error));
    }
  }

  // --- import -------------------------------------------------------------

  MultipartFile _csvFile(Uint8List bytes, String fileName) =>
      MultipartFile.fromBytes(bytes, filename: fileName);

  Future<ImportPreview> previewImport(
    String pageId, {
    required Uint8List bytes,
    required String fileName,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/pages/$pageId/import/preview',
      data: FormData.fromMap({'file': _csvFile(bytes, fileName)}),
    );
    return ImportPreview.fromJson(response.data!);
  });

  Future<ImportValidation> validateImport(
    String pageId, {
    required Uint8List bytes,
    required String fileName,
    required ImportMapping mapping,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/pages/$pageId/import/validate',
      data: FormData.fromMap({
        'file': _csvFile(bytes, fileName),
        'payload': jsonEncode(mapping.toJson()),
      }),
    );
    return ImportValidation.fromJson(response.data!);
  });

  Future<ImportCommitResult> commitImport(
    String pageId, {
    required Uint8List bytes,
    required String fileName,
    required ImportMapping mapping,
  }) => mapApiErrors(() async {
    final response = await dio.post<Map<String, dynamic>>(
      '/pages/$pageId/import/commit',
      data: FormData.fromMap({
        'file': _csvFile(bytes, fileName),
        'payload': jsonEncode(mapping.toJson()),
      }),
    );
    return ImportCommitResult.fromJson(response.data!);
  });

  Future<List<ImportBatch>> listImportBatches(String pageId) => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/pages/$pageId/import-batches');
    return response.data!.cast<Map<String, dynamic>>().map(ImportBatch.fromJson).toList();
  });

  Future<void> rollbackImport(String batchId) => mapApiErrors(() async {
    await dio.post<void>('/import-batches/$batchId/rollback');
  });

  // --- reference pickers ---------------------------------------------------

  /// Feeds `STORE_REF` field renderers. Owners see every store; a manager
  /// sees only their assigned ones — the server filters (plan section 4.5),
  /// this just renders whatever comes back.
  Future<List<Store>> listStores() => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/stores');
    return response.data!.cast<Map<String, dynamic>>().map(Store.fromJson).toList();
  });

  /// Feeds `USER_REF` field renderers and the access editor. Owner-only on
  /// the server (plan section 4.2) — a manager's call here 403s, and the
  /// `USER_REF` renderer degrades to showing the stored id (see the P3 plan's
  /// "known limitations" section).
  Future<List<User>> listUsers() => mapApiErrors(() async {
    final response = await dio.get<List<dynamic>>('/users');
    return response.data!.cast<Map<String, dynamic>>().map(User.fromJson).toList();
  });
}
