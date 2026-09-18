import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../auth/domain/user.dart';
import '../application/pages_providers.dart';
import '../domain/page.dart';

/// The Owner grants managers access to a page (plan sections 3.10, 3.17,
/// 4.3) — `PUT /pages/{id}/access` replaces the grant list wholesale, so
/// this screen always hydrates from [pageAccessProvider] first: without
/// that, every save would silently wipe out managers the Owner didn't mean
/// to touch (the bug this screen used to have — see its old docstring in
/// git history, and `GET /pages/{id}/access` on the backend that closes it).
class AccessEditorScreen extends ConsumerStatefulWidget {
  const AccessEditorScreen({super.key, required this.pageId});

  final String pageId;

  @override
  ConsumerState<AccessEditorScreen> createState() => _AccessEditorScreenState();
}

class _AccessEditorScreenState extends ConsumerState<AccessEditorScreen> {
  final Map<String, bool> _canView = {};
  final Map<String, bool> _canCreate = {};
  bool _hydrated = false;
  bool _isSubmitting = false;
  String? _error;

  void _hydrateOnce(List<AccessGrant> grants) {
    if (_hydrated) return;
    _hydrated = true;
    for (final grant in grants) {
      _canView[grant.userId] = grant.canView;
      _canCreate[grant.userId] = grant.canCreate;
    }
  }

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
      // A manager's Pages list is server-filtered by these grants (plan
      // section 4.3) — without this, a newly granted manager wouldn't see
      // the page appear until something else happened to invalidate it.
      ref.invalidate(pagesProvider);
      ref.invalidate(pageAccessProvider(widget.pageId));
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(content: Text('Access updated')));
      Navigator.of(context).pop();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final usersAsync = ref.watch(usersProvider);
    final accessAsync = ref.watch(pageAccessProvider(widget.pageId));

    return Scaffold(
      appBar: AppBar(title: const Text('Manage access')),
      body: usersAsync.when(
        data: (users) => accessAsync.when(
          data: (grants) {
            _hydrateOnce(grants);
            final managers = users.where((u) => u.role == UserRole.manager).toList();
            return Column(
              children: [
                Card(
                  margin: const EdgeInsets.all(16),
                  color: Theme.of(context).colorScheme.secondaryContainer,
                  child: const Padding(
                    padding: EdgeInsets.all(12),
                    child: Text(
                      'Managers won\'t see this page until access is granted. '
                      'Saving replaces every manager\'s access for this page — '
                      'check Can view / Can add records for everyone who should keep it.',
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
                                      subtitle: const Text('Can view'),
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
          loading: () => const AppLoadingState(),
          error: (error, _) => AppErrorState(
            message: '$error',
            onRetry: () => ref.invalidate(pageAccessProvider(widget.pageId)),
          ),
        ),
        loading: () => const AppLoadingState(),
        error: (error, _) => AppErrorState(
          message: '$error',
          onRetry: () => ref.invalidate(usersProvider),
        ),
      ),
    );
  }
}
