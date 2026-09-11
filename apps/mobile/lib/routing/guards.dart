import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/application/auth_controller.dart';

/// Bridges Riverpod state changes into go_router's `refreshListenable`,
/// since go_router only re-evaluates `redirect` when told to.
///
/// This is a **UI-routing convenience only** — it decides which screen to
/// show, never what the user is allowed to do. Every real permission check
/// happens in FastAPI (plan section 4.2): "Flutter hides buttons; Flutter
/// never decides anything."
class RouterRefreshNotifier extends ChangeNotifier {
  RouterRefreshNotifier(Ref ref) {
    ref.listen<AuthState>(authControllerProvider, (previous, next) {
      notifyListeners();
    });
  }
}

/// Where an unauthenticated / authenticated user should land, given the
/// route they were trying to reach. Returns null to allow the navigation
/// through unchanged.
String? authRedirect(AuthState state, String currentLocation) {
  final isAuthRoute = currentLocation == '/login';

  if (state is AuthChecking) {
    // Stay put while the startup /me check resolves — redirecting on every
    // rebuild here would otherwise bounce the user between screens.
    return null;
  }

  if (state is AuthUnauthenticated) {
    return isAuthRoute ? null : '/login';
  }

  // Authenticated: never show the login screen again.
  return isAuthRoute ? '/home' : null;
}
