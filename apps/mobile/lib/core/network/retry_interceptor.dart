import 'dart:async';
import 'dart:math';

import 'package:dio/dio.dart';

/// Retries transient network failures with exponential backoff.
///
/// A `GET` is always safe to retry. A `POST`/`PATCH`/`DELETE` is only retried
/// when the caller has supplied an `Idempotency-Key` header — plan section
/// 21.1's idempotency guarantee is exactly what makes a blind retry of a
/// write safe; without that header a retried write could double-post.
class RetryInterceptor extends Interceptor {
  RetryInterceptor({
    required this.dio,
    this.maxAttempts = 3,
    this.baseDelay = const Duration(milliseconds: 300),
  });

  final Dio dio;
  final int maxAttempts;
  final Duration baseDelay;

  bool _isRetriable(DioException err) {
    final isTransient =
        err.type == DioExceptionType.connectionTimeout ||
        err.type == DioExceptionType.receiveTimeout ||
        err.type == DioExceptionType.connectionError ||
        (err.response?.statusCode ?? 0) >= 500;
    if (!isTransient) return false;

    final method = err.requestOptions.method.toUpperCase();
    if (method == 'GET' || method == 'HEAD') return true;

    return err.requestOptions.headers.containsKey('Idempotency-Key');
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final attempt = (err.requestOptions.extra['velmart_attempt'] as int?) ?? 0;

    if (!_isRetriable(err) || attempt >= maxAttempts) {
      handler.next(err);
      return;
    }

    final delay = baseDelay * pow(2, attempt).toInt();
    await Future<void>.delayed(delay);

    try {
      final retryOptions = err.requestOptions.copyWith(
        extra: {
          ...err.requestOptions.extra,
          'velmart_attempt': attempt + 1,
        },
      );
      final response = await dio.fetch<dynamic>(retryOptions);
      handler.resolve(response);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }
}
