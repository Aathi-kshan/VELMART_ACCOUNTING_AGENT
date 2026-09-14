import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/permissions/can.dart';
import '../application/auth_controller.dart';

/// The More tab (plan section 22.4). Content only — `AppShell` owns the
/// `Scaffold`/`AppBar`.
///
/// Deliberately short: Settings and Users are later phases, and per plan
/// section 22.4 "a greyed-out feature invites requests for access; an
/// absent one does not" — so they simply aren't listed yet rather than
/// shown disabled. Audit arrived in P5.
class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    final user = state is AuthAuthenticated ? state.user : null;

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (user != null)
          Card(
            child: ListTile(
              leading: const Icon(Icons.person_outline),
              title: Text(user.fullName),
              subtitle: Text(user.email),
            ),
          ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.balance_outlined),
            title: const Text('Reconciliation'),
            onTap: () => context.pushNamed('reconciliation'),
          ),
        ),
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.history),
            title: const Text('Audit log'),
            onTap: () => context.pushNamed('audit'),
          ),
        ),
        if (user != null && canUseAi(user.role)) ...[
          const SizedBox(height: 8),
          Card(
            child: ListTile(
              leading: const Icon(Icons.chat_bubble_outline),
              title: const Text('Ask about your business'),
              onTap: () => context.pushNamed('ai'),
            ),
          ),
        ],
        const SizedBox(height: 8),
        Card(
          child: ListTile(
            leading: const Icon(Icons.logout),
            title: const Text('Sign out'),
            onTap: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ),
      ],
    );
  }
}
