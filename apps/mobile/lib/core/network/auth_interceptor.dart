import 'dart:async';

import 'package:dio/dio.dart';

import '../storage/secure_store.dart';

/// Attaches the bearer token to every request and refreshes it exactly once
/// on a 401 before giving up (plan section 20.2).
///
/// Concurrent requests that all hit a 401 at once must not each fire their
/// own refresh call — a stale refresh token would then be replayed by the
/// second caller and read as theft (`TokenReuseError`), revoking the whole
/// device family for no reason. A single in-flight `Future` is shared by
/// every waiter instead.
class AuthInterceptor extends Interceptor {
  AuthInterceptor({required this.dio, required this.secureStore});

  final Dio dio;
  final SecureStore secureStore;

  Future<bool>? _refreshInFlight;

  static const _noAuthPaths = {'/auth/login', '/auth/refresh'};

  bool _needsAuth(RequestOptions options) =>
      !_noAuthPaths.any((p) => options.path.endsWith(p));

  @override
  Future<void> onRequest(
    RequestOptions options,
    RequestInterceptorHandler handler,
  ) async {
    if (_needsAuth(options)) {
      final token = await secureStore.accessToken;
      if (token != null) {
        options.headers['Authorization'] = 'Bearer $token';
      }
    }
    handler.next(options);
  }

  @override
  Future<void> onError(
    DioException err,
    ErrorInterceptorHandler handler,
  ) async {
    final response = err.response;
    final options = err.requestOptions;

    final isUnauthorized = response?.statusCode == 401;
    final alreadyRetried = options.extra['velmart_retried'] == true;

    if (!isUnauthorized || alreadyRetried || !_needsAuth(options)) {
      handler.next(err);
      return;
    }

    final refreshed = await _refresh();
    if (!refreshed) {
      // The refresh token is dead too — the caller must send the user back
      // to the login screen. Cached tokens are cleared so nothing retries
      // with a value the server has already rejected.
      await secureStore.clear();
      handler.next(err);
      return;
    }

    try {
      final token = await secureStore.accessToken;
      final retryOptions = options.copyWith(
        extra: {...options.extra, 'velmart_retried': true},
      );
      if (token != null) {
        retryOptions.headers['Authorization'] = 'Bearer $token';
      }
      final retryResponse = await dio.fetch<dynamic>(retryOptions);
      handler.resolve(retryResponse);
    } on DioException catch (retryError) {
      handler.next(retryError);
    }
  }

  /// Refresh the access token, coalescing concurrent callers onto one call.
  Future<bool> _refresh() {
    return _refreshInFlight ??= _doRefresh().whenComplete(() {
      _refreshInFlight = null;
    });
  }

  Future<bool> _doRefresh() async {
    final refreshToken = await secureStore.refreshToken;
    if (refreshToken == null) return false;

    try {
      final response = await dio.post<Map<String, dynamic>>(
        '/auth/refresh',
        data: {'refresh_token': refreshToken},
      );
      final body = response.data;
      if (body == null) return false;

      await secureStore.saveTokens(
        accessToken: body['access_token'] as String,
        refreshToken: body['refresh_token'] as String,
      );
      return true;
    } on DioException {
      return false;
    }
  }
}
