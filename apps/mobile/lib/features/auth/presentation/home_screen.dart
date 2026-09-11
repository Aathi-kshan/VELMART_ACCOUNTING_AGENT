import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../application/auth_controller.dart';
import '../domain/user.dart';

/// The P1 destination: display name and role, proving login end to end.
/// Later phases replace this with the real page-list home (plan section 22).
class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    final user = state is AuthAuthenticated ? state.user : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Velmart'),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sign out',
            onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          ),
        ],
      ),
      body: Center(
        child: user == null
            ? const CircularProgressIndicator()
            : Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(user.fullName, style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: 8),
                  Chip(
                    label: Text(user.role == UserRole.owner ? 'Owner' : 'Manager'),
                  ),
                ],
              ),
      ),
    );
  }
}
