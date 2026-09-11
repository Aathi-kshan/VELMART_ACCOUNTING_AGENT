import 'package:dio/dio.dart';

import '../config/env.dart';
import '../storage/secure_store.dart';
import 'auth_interceptor.dart';
import 'retry_interceptor.dart';

/// The single Dio instance the app talks to the API through.
///
/// Every request carries the bearer token (via [AuthInterceptor]); a 401
/// triggers exactly one refresh attempt before failing; transient network
/// errors are retried (via [RetryInterceptor]).
class ApiClient {
  ApiClient({SecureStore? secureStore})
    : secureStore = secureStore ?? SecureStore(),
      dio = Dio(
        BaseOptions(
          baseUrl: '${Env.apiBaseUrl}/v1',
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 15),
          contentType: 'application/json',
        ),
      ) {
    dio.interceptors.addAll([
      AuthInterceptor(dio: dio, secureStore: this.secureStore),
      RetryInterceptor(dio: dio),
    ]);
  }

  final Dio dio;
  final SecureStore secureStore;
}
