import 'package:dio/dio.dart';
import 'package:uuid/uuid.dart';

import '../../../core/storage/secure_store.dart';
import '../domain/user.dart';

/// Thrown for any login/refresh failure. The server deliberately returns the
/// same generic message for wrong password, unknown email, and a locked
/// account (plan section 20.2) — the client must not try to distinguish them.
class AuthException implements Exception {
  const AuthException(this.message);
  final String message;

  @override
  String toString() => message;
}

class AuthRepository {
  AuthRepository({required this.dio, required this.secureStore});

  final Dio dio;
  final SecureStore secureStore;
  final _uuid = Uuid();

  Future<String> _ensureDeviceId() async {
    final existing = await secureStore.deviceId;
    if (existing != null) return existing;
    final generated = _uuid.v4();
    await secureStore.saveDeviceId(generated);
    return generated;
  }

  Future<User> login({required String email, required String password}) async {
    final deviceId = await _ensureDeviceId();
    try {
      final response = await dio.post<Map<String, dynamic>>(
        '/auth/login',
        data: {'email': email, 'password': password, 'device_id': deviceId},
      );
      return _saveAndParse(response.data!);
    } on DioException catch (e) {
      throw AuthException(_messageFor(e));
    }
  }

  Future<User> fetchMe() async {
    final response = await dio.get<Map<String, dynamic>>('/me');
    return User.fromJson(response.data!);
  }

  Future<void> logout() async {
    final refreshToken = await secureStore.refreshToken;
    if (refreshToken != null) {
      try {
        await dio.post<void>('/auth/logout', data: {'refresh_token': refreshToken});
      } on DioException {
        // Logout is best-effort client-side regardless — the token is
        // cleared below either way, matching the server's idempotent logout.
      }
    }
    await secureStore.clear();
  }

  Future<User> _saveAndParse(Map<String, dynamic> body) async {
    await secureStore.saveTokens(
      accessToken: body['access_token'] as String,
      refreshToken: body['refresh_token'] as String,
    );
    return User.fromJson(body['user'] as Map<String, dynamic>);
  }

  String _messageFor(DioException e) {
    if (e.response?.statusCode == 429) {
      return 'Too many attempts. Please wait a moment and try again.';
    }
    final detail = e.response?.data is Map
        ? (e.response!.data as Map)['detail'] as String?
        : null;
    return detail ?? 'Invalid email or password.';
  }
}
