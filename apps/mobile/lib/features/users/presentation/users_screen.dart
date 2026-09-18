import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/network/api_exception.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_radii.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/app_card.dart';
import '../../../core/widgets/app_error_state.dart';
import '../../../core/widgets/app_loading_state.dart';
import '../../../core/widgets/empty_state.dart';
import '../../../core/widgets/refreshable.dart';
import '../../auth/application/auth_controller.dart';
import '../../auth/domain/user.dart';
import '../../pages/application/pages_providers.dart';

class UsersScreen extends ConsumerWidget {
  const UsersScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final users = ref.watch(usersProvider);
    final me = ref.watch(authControllerProvider);
    final current = me is AuthAuthenticated ? me.user : null;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Users'),
        actions: [
          IconButton(
            tooltip: 'Add user',
            onPressed: () => _openEditor(context, ref),
            icon: const Icon(Icons.person_add_outlined),
          ),
        ],
      ),
      body: users.when(
        loading: () => PullToRefresh(
          onRefresh: () async => ref.invalidate(usersProvider),
          child: const AppLoadingState(),
        ),
        error: (error, _) => PullToRefresh(
          onRefresh: () async => ref.invalidate(usersProvider),
          child: AppErrorState(
            message: error is ApiException ? error.detail : '$error',
            onRetry: () => ref.invalidate(usersProvider),
          ),
        ),
        data: (list) {
          return PullToRefresh(
            onRefresh: () async => ref.invalidate(usersProvider),
            childScrolls: true,
            child: ListView(
              padding: const EdgeInsets.fromLTRB(
                AppSpacing.md,
                AppSpacing.md,
                AppSpacing.md,
                AppSpacing.xxl,
              ),
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: FilledButton.icon(
                    onPressed: () => _openEditor(context, ref),
                    icon: const Icon(Icons.add, size: 18),
                    label: const Text('Add user'),
                  ),
                ),
                const SizedBox(height: AppSpacing.md),
                if (list.isEmpty)
                  const EmptyState(
                    title: 'No users',
                    message: 'Create a manager so they can enter records.',
                  )
                else
                  for (final user in list) ...[
                    AppCard(
                      onTap: () => _openEditor(context, ref, existing: user),
                      padding: const EdgeInsets.all(
                        AppSpacing.cardPaddingDense,
                      ),
                      child: Row(
                        children: [
                          CircleAvatar(
                            backgroundColor: user.role == UserRole.owner
                                ? AppColors.brandPrimaryDark
                                : AppColors.brandSecondarySoft,
                            foregroundColor: user.role == UserRole.owner
                                ? AppColors.textOnBrand
                                : AppColors.brandSecondaryDark,
                            child: Text(
                              user.fullName.isEmpty
                                  ? '?'
                                  : user.fullName[0].toUpperCase(),
                              style: const TextStyle(
                                fontWeight: FontWeight.w600,
                              ),
                            ),
                          ),
                          const SizedBox(width: AppSpacing.smMd),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  user.fullName,
                                  style: Theme.of(context)
                                      .textTheme
                                      .titleMedium,
                                ),
                                Text(
                                  user.role == UserRole.owner
                                      ? 'Owner'
                                      : 'Manager',
                                  style: Theme.of(context).textTheme.bodySmall,
                                ),
                              ],
                            ),
                          ),
                          if (current?.id == user.id)
                            Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 9,
                                vertical: 6,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.brandPrimarySoft,
                                borderRadius: AppRadii.pillRadius,
                              ),
                              child: Text(
                                'You',
                                style: Theme.of(context).textTheme.labelMedium
                                    ?.copyWith(
                                      color: AppColors.brandPrimaryDeep,
                                      fontWeight: FontWeight.w600,
                                    ),
                              ),
                            ),
                        ],
                      ),
                    ),
                    const SizedBox(height: AppSpacing.sm),
                  ],
              ],
            ),
          );
        },
      ),
    );
  }

  Future<void> _openEditor(
    BuildContext context,
    WidgetRef ref, {
    User? existing,
  }) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) => _UserEditor(existing: existing),
    );
    ref.invalidate(usersProvider);
  }
}

class _UserEditor extends ConsumerStatefulWidget {
  const _UserEditor({this.existing});

  final User? existing;

  @override
  ConsumerState<_UserEditor> createState() => _UserEditorState();
}

class _UserEditorState extends ConsumerState<_UserEditor> {
  final _formKey = GlobalKey<FormState>();
  late final _name = TextEditingController(
    text: widget.existing?.fullName ?? '',
  );
  late final _email = TextEditingController(text: widget.existing?.email ?? '');
  final _password = TextEditingController();
  late UserRole _role = widget.existing?.role ?? UserRole.manager;
  String? _error;
  bool _saving = false;

  @override
  void dispose() {
    _name.dispose();
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _save() async {
    if (!_formKey.currentState!.validate()) return;
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final repo = ref.read(pageRepositoryProvider);
      if (widget.existing == null) {
        await repo.createUser(
          email: _email.text.trim(),
          password: _password.text,
          fullName: _name.text.trim(),
          role: _role,
        );
      } else {
        await repo.updateUser(
          widget.existing!.id,
          fullName: _name.text.trim(),
          role: _role,
        );
      }
      if (mounted) Navigator.of(context).pop();
    } on ApiException catch (e) {
      setState(() => _error = e.detail);
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.viewInsetsOf(context).bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        bottom + AppSpacing.md,
      ),
      child: Form(
        key: _formKey,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.existing == null ? 'Add user' : 'Edit user',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: AppSpacing.md),
            TextFormField(
              controller: _name,
              decoration: const InputDecoration(labelText: 'Full name'),
              validator: (v) =>
                  (v == null || v.trim().isEmpty) ? 'Name is required' : null,
            ),
            const SizedBox(height: AppSpacing.smMd),
            TextFormField(
              controller: _email,
              enabled: widget.existing == null,
              decoration: const InputDecoration(labelText: 'Email'),
              validator: (v) => (v == null || !v.contains('@'))
                  ? 'Enter a valid email'
                  : null,
            ),
            if (widget.existing == null) ...[
              const SizedBox(height: AppSpacing.smMd),
              TextFormField(
                controller: _password,
                obscureText: true,
                decoration: const InputDecoration(labelText: 'Password'),
                validator: (v) => (v == null || v.length < 10)
                    ? 'At least 10 characters'
                    : null,
              ),
            ],
            const SizedBox(height: AppSpacing.smMd),
            DropdownButtonFormField<UserRole>(
              initialValue: _role,
              decoration: const InputDecoration(labelText: 'Role'),
              items: const [
                DropdownMenuItem(
                  value: UserRole.manager,
                  child: Text('Manager'),
                ),
                DropdownMenuItem(value: UserRole.owner, child: Text('Owner')),
              ],
              onChanged: (next) => setState(() => _role = next ?? _role),
            ),
            if (_error != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(_error!, style: const TextStyle(color: AppColors.error)),
            ],
            const SizedBox(height: AppSpacing.md),
            FilledButton(
              onPressed: _saving ? null : _save,
              child: Text(widget.existing == null ? 'Create user' : 'Save'),
            ),
          ],
        ),
      ),
    );
  }
}
