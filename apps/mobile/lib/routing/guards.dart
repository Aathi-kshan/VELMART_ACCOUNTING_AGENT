import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../features/auth/application/auth_controller.dart';
import '../features/auth/domain/user.dart';

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

/// Owner-only paths the Manager chrome never links to. Redirecting these
/// hides the screen; FastAPI still enforces the real 403.
bool isOwnerOnlyLocation(String location) {
  if (location == '/ai' || location.startsWith('/ai/')) return true;
  if (location == '/users' || location.startsWith('/users/')) return true;
  if (location == '/pages/new') return true;
  if (RegExp(r'^/pages/[^/]+/columns').hasMatch(location)) return true;
  if (RegExp(r'^/pages/[^/]+/access').hasMatch(location)) return true;
  if (RegExp(r'^/records/[^/]+/edit').hasMatch(location)) return true;
  return false;
}

bool isRecordListLocation(String location) =>
    RegExp(r'^/pages/[^/]+/records$').hasMatch(location);

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

  if (state is AuthAuthenticated) {
    if (isAuthRoute) return '/home';
    if (state.user.role != UserRole.owner && isOwnerOnlyLocation(currentLocation)) {
      return '/home';
    }
    return null;
  }

  return isAuthRoute ? '/home' : null;
}
