import 'package:flutter_riverpod/flutter_riverpod.dart';

import 'network/api_client.dart';
import 'storage/secure_store.dart';

/// Cross-cutting singletons. Kept separate from the classes themselves so
/// `ApiClient` and `SecureStore` stay framework-agnostic and unit-testable
/// without a `ProviderContainer`.
final secureStoreProvider = Provider<SecureStore>((ref) => SecureStore());

final apiClientProvider = Provider<ApiClient>((ref) {
  return ApiClient(secureStore: ref.watch(secureStoreProvider));
});
