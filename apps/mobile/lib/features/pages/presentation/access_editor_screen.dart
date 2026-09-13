import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';

/// The Owner grants managers access to a page (plan sections 3.10, 3.17,
/// 4.3) — `PUT /pages/{id}/access` replaces the grant list wholesale.
///
/// **Known backend gap, not a client bug:** there is no `GET
/// /pages/{id}/access` — the API only supports writing grants, never
/// reading the current ones back. So this screen cannot show which managers
/// are already granted; it starts every manager unchecked and warns,
/// loudly, that saving replaces access for this page entirely. Worth a
/// small follow-up on the backend (a list-grants endpoint) so this can show
/// real state instead.
class AccessEditorScreen extends ConsumerStatefulWidget {
  const AccessEditorScreen({super.key, required this.pageId});

  final String pageId;

  @override
  ConsumerState<AccessEditorScreen> createState() => _AccessEditorScreenState();
}

class _AccessEditorScreenState extends ConsumerState<AccessEditorScreen> {
  final Map<String, bool> _canView = {};
  final Map<String, bool> _canCreate = {};
  bool _isSubmitting = false;
  String? _error;

  Future<void> _save(List<User> managers) async {
    setState(() {
      _isSubmitting = true;
      _error = null;
    });
    try {
      final grants = [
        for (final manager in managers)
          if (_canView[manager.id] == true)
            AccessGrant(
              userId: manager.id,
              canView: true,
              canCreate: _canCreate[manager.id] == true,
            ),
      ];
      await ref.read(pageRepositoryProvider).setAccess(widget.pageId, grants);
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final usersAsync = ref.watch(usersProvider);

    return Scaffold(
      appBar: AppBar(title: const Text('Manage access')),
      body: usersAsync.when(
        data: (users) {
          final managers = users.where((u) => u.role == UserRole.manager).toList();
          return Column(
            children: [
              Card(
                margin: const EdgeInsets.all(16),
                color: Theme.of(context).colorScheme.secondaryContainer,
                child: const Padding(
                  padding: EdgeInsets.all(12),
                  child: Text(
                    'Saving replaces every manager\'s access to this page. Check '
                    'everyone who should be able to see it, including anyone who '
                    'already could — this always starts from a blank slate.',
                  ),
                ),
              ),
              if (_error != null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ),
              Expanded(
                child: managers.isEmpty
                    ? const Center(child: Text('No managers to grant access to yet.'))
                    : ListView.builder(
                        itemCount: managers.length,
                        itemBuilder: (context, index) {
                          final manager = managers[index];
                          final canView = _canView[manager.id] ?? false;
                          final canCreate = _canCreate[manager.id] ?? false;
                          return Card(
                            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8),
                              child: Column(
                                children: [
                                  CheckboxListTile(
                                    title: Text(manager.fullName),
                                    subtitle: Text(manager.email),
                                    value: canView,
                                    onChanged: (next) => setState(() {
                                      _canView[manager.id] = next ?? false;
                                      if (next != true) _canCreate[manager.id] = false;
                                    }),
                                  ),
                                  CheckboxListTile(
                                    title: const Text('Can add records'),
                                    value: canCreate,
                                    onChanged: canView
                                        ? (next) => setState(() => _canCreate[manager.id] = next ?? false)
                                        : null,
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
              ),
              Padding(
                padding: const EdgeInsets.all(16),
                child: FilledButton(
                  onPressed: _isSubmitting ? null : () => _save(managers),
                  child: _isSubmitting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Save access'),
                ),
              ),
            ],
          );
        },
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (error, _) => Center(child: Text('Could not load users.\n$error')),
      ),
    );
  }
}
