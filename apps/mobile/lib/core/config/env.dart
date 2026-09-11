/// Build-time configuration.
///
/// The API base URL, injected via `--dart-define=API_BASE_URL=...` at build
/// time. Defaults to the local development API (`docs/API.md` base:
/// `https://<railway-domain>/v1` in production).
class Env {
  Env._();

  static const String apiBaseUrl = String.fromEnvironment(
    'API_BASE_URL',
    defaultValue: 'http://localhost:8000',
  );

  /// Whether this build should trust an unpinned certificate — true only for
  /// local development against a plain-HTTP API. Production always uses TLS
  /// with certificate pinning on mobile (plan section 20.3).
  static const bool isDevelopment = apiBaseUrl == 'http://localhost:8000';
}
