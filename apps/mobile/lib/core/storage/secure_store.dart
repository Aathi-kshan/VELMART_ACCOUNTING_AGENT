import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Keychain (iOS/macOS) / Keystore (Android) / Credential Manager (Windows)
/// backed storage for auth tokens.
///
/// Nothing sensitive is ever written to shared preferences or the Drift
/// cache — only here. Cleared on logout (plan section 19.2).
class SecureStore {
  SecureStore({FlutterSecureStorage? storage})
    : _storage =
          storage ??
          const FlutterSecureStorage(
            aOptions: AndroidOptions(encryptedSharedPreferences: true),
          );

  final FlutterSecureStorage _storage;

  static const _accessTokenKey = 'velmart.access_token';
  static const _refreshTokenKey = 'velmart.refresh_token';
  static const _deviceIdKey = 'velmart.device_id';

  Future<String?> get accessToken => _storage.read(key: _accessTokenKey);
  Future<String?> get refreshToken => _storage.read(key: _refreshTokenKey);
  Future<String?> get deviceId => _storage.read(key: _deviceIdKey);

  Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(key: _accessTokenKey, value: accessToken);
    await _storage.write(key: _refreshTokenKey, value: refreshToken);
  }

  Future<void> saveDeviceId(String deviceId) =>
      _storage.write(key: _deviceIdKey, value: deviceId);

  /// Clears every stored token. Called on logout and on refresh-token
  /// failure — a device family revoked for token reuse must not keep trying
  /// with the now-dead refresh token (plan section 20.2).
  Future<void> clear() async {
    await _storage.delete(key: _accessTokenKey);
    await _storage.delete(key: _refreshTokenKey);
    // deviceId is deliberately kept: it identifies this installation, not
    // this session, and re-login should not look like a new device.
  }
}
