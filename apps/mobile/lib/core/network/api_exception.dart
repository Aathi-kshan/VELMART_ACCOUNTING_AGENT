import 'dart:convert';

import 'package:dio/dio.dart';

/// One API error, decoded from RFC 9457 problem details (plan section 21.1).
///
/// The server answers every failure with the same shape, so the client never
/// has to guess:
///
/// ```json
/// { "type": "https://velmart.app/errors/validation-failed",
///   "title": "Validation failed",
///   "status": 422,
///   "detail": "The record data did not match this page's schema.",
///   "code": "VALIDATION_FAILED",
///   "request_id": "01J8...",
///   "errors": [ { "loc": ["category"], "msg": "Input should be 'Rent'" } ] }
/// ```
///
/// `code` is the contract to branch on — never `detail`, which is prose meant
/// for a person (docs/API.md section 1.4). `detail` is what to *show*.
class ApiException implements Exception {
  const ApiException({
    required this.statusCode,
    required this.code,
    required this.detail,
    this.fieldErrors = const {},
    this.extra = const {},
  });

  /// HTTP status, or 0 when the request never reached the server.
  final int statusCode;

  /// The stable machine-readable code (`VALIDATION_FAILED`,
  /// `VERSION_CONFLICT`, `RESERVED_PAGE_KEY`, ...). Empty for transport
  /// failures that produced no problem-details body.
  final String code;

  /// Human-readable message, safe to render directly.
  final String detail;

  /// Column key -> message, built from a 422's `errors` list. This is what
  /// puts the server's own validation message under the right form field.
  final Map<String, String> fieldErrors;

  /// Anything else the problem body carried — e.g. `current_version` on a
  /// 409 `VERSION_CONFLICT`, or `would_fail` on a narrowing rejection.
  final Map<String, dynamic> extra;

  bool get isValidationFailure => statusCode == 422;
  bool get isVersionConflict => code == 'VERSION_CONFLICT';
  bool get isNotFound => statusCode == 404;
  bool get isForbidden => statusCode == 403;

  /// The row's current version, when the server rejected an optimistic-lock
  /// mismatch and told us what it actually holds.
  int? get currentVersion {
    final value = extra['current_version'];
    return value is int ? value : null;
  }

  /// Decode a Dio failure. Falls back to a generic message when the response
  /// is not problem+json (a proxy error page, a dropped connection).
  factory ApiException.fromDio(DioException error) {
    final response = error.response;
    final data = response?.data;

    if (data is! Map) {
      return ApiException(
        statusCode: response?.statusCode ?? 0,
        code: '',
        detail: _transportMessage(error),
      );
    }

    final body = data.cast<String, dynamic>();
    return ApiException(
      statusCode: response?.statusCode ?? 0,
      code: body['code'] as String? ?? '',
      detail: body['detail'] as String? ?? _transportMessage(error),
      fieldErrors: _fieldErrorsFrom(body['errors']),
      extra: body,
    );
  }

  /// `errors` arrives as Pydantic's own list — `loc` is a path, and for a
  /// record write its first element is the column key (the server validates
  /// `data` against a model built from `page_columns`, so `loc` is
  /// `["category"]`, not `["body", "data", "category"]`).
  static Map<String, String> _fieldErrorsFrom(Object? errors) {
    if (errors is! List) return const {};

    final mapped = <String, String>{};
    for (final entry in errors) {
      if (entry is! Map) continue;
      final loc = entry['loc'];
      final message = entry['msg'];
      if (loc is! List || loc.isEmpty || message is! String) continue;

      // Skip the framework's own request-shape errors ("body", "query") and
      // key on the last non-framework segment, which is the column.
      final segments = loc
          .whereType<String>()
          .where((s) => s != 'body' && s != 'query' && s != 'data')
          .toList();
      if (segments.isEmpty) continue;

      // First message per field wins: the form shows one line per field.
      mapped.putIfAbsent(segments.last, () => message);
    }
    return mapped;
  }

  static String _transportMessage(DioException error) {
    switch (error.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return 'The server took too long to respond. Please try again.';
      case DioExceptionType.connectionError:
        return 'Cannot reach the server. Check your connection.';
      default:
        final status = error.response?.statusCode;
        if (status != null && status >= 500) {
          return 'Something went wrong on the server. Please try again.';
        }
        return 'Something went wrong. Please try again.';
    }
  }

  @override
  String toString() => detail;
}

/// Run an API call, turning any [DioException] into an [ApiException].
///
/// Every repository method wraps its request in this so screens only ever
/// catch one exception type.
Future<T> mapApiErrors<T>(Future<T> Function() request) async {
  try {
    return await request();
  } on DioException catch (error) {
    throw ApiException.fromDio(error);
  }
}

/// `responseType: bytes` (a CSV/file download) is what lets a *successful*
/// response come back as raw bytes rather than Dio trying — and failing —
/// to JSON-decode a `text/csv` body. But it means an *error* response
/// arrives as raw bytes too, not the auto-parsed `Map` [ApiException.fromDio]
/// expects. Decode it back to JSON first so a 403 here still surfaces as
/// "Owners only", not a generic transport message — the same fix
/// `page_repository.dart`'s CSV export needed, shared here so a second
/// bytes-returning endpoint (the audit log export) doesn't need its own copy.
DioException decodeBytesResponseError(DioException error) {
  final raw = error.response?.data;
  if (raw is! List<int>) return error;
  try {
    final decoded = jsonDecode(utf8.decode(raw));
    final patchedResponse = Response<dynamic>(
      requestOptions: error.requestOptions,
      data: decoded,
      statusCode: error.response?.statusCode,
      statusMessage: error.response?.statusMessage,
      headers: error.response?.headers,
    );
    return DioException(
      requestOptions: error.requestOptions,
      response: patchedResponse,
      type: error.type,
      error: error.error,
      message: error.message,
    );
  } catch (_) {
    return error;
  }
}
