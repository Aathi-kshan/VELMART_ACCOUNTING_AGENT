import 'dart:typed_data';

import 'package:dio/dio.dart';

import '../../../core/network/api_exception.dart';
import '../../pages/domain/record.dart' show Paginated;
import '../domain/audit_log_entry.dart';

/// `GET /audit-logs` / `GET /audit-logs/export` (plan section 18.3, P5).
/// Thin, like `PageRepository`: no validation, no decisions, just send and
/// parse. A manager gets a real, view-gated subset back rather than a 403
/// (the server does the filtering — see `app/services/audit_read_service.py`);
/// the export button is only ever shown to an Owner (`canExportAuditLog`).
class AuditRepository {
  AuditRepository({required this.dio});

  final Dio dio;

  Future<Paginated<AuditLogEntry>> listAuditLogs({
    AuditLogFilters filters = const AuditLogFilters(),
    String? cursor,
    int limit = 50,
  }) => mapApiErrors(() async {
    final response = await dio.get<Map<String, dynamic>>(
      '/audit-logs',
      queryParameters: {
        ...filters.toQueryParameters(),
        if (cursor != null) 'cursor': cursor,
        'limit': limit,
      },
    );
    return Paginated.fromJson(response.data!, AuditLogEntry.fromJson);
  });

  /// Every entry matching `filters`, not just the current page — the
  /// server walks its own cursor internally (plan section 18.3:
  /// "Exportable by the Owner").
  Future<Uint8List> exportAuditLogs({AuditLogFilters filters = const AuditLogFilters()}) async {
    try {
      final response = await dio.get<List<int>>(
        '/audit-logs/export',
        queryParameters: filters.toQueryParameters(),
        options: Options(responseType: ResponseType.bytes),
      );
      return Uint8List.fromList(response.data!);
    } on DioException catch (error) {
      throw ApiException.fromDio(decodeBytesResponseError(error));
    }
  }
}
