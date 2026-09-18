import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/permissions/can.dart';
import '../../../core/theme/app_colors.dart';
import '../../../core/theme/app_spacing.dart';
import '../../../core/widgets/app_card.dart';
import '../application/auth_controller.dart';

class MoreScreen extends ConsumerWidget {
  const MoreScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(authControllerProvider);
    final user = state is AuthAuthenticated ? state.user : null;
    if (user == null) return const SizedBox.shrink();

    return ListView(
      padding: const EdgeInsets.fromLTRB(AppSpacing.md, AppSpacing.md, AppSpacing.md, AppSpacing.xxl),
      children: [
        Text('More', style: Theme.of(context).textTheme.headlineLarge),
        const SizedBox(height: AppSpacing.md),
        Text('USERS & ACCESS', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textSecondary)),
        const SizedBox(height: AppSpacing.sm),
        if (canManageUsers(user.role)) ...[
          AppCard(
            onTap: () => context.pushNamed('users'),
            padding: EdgeInsets.zero,
            child: const ListTile(
              leading: Icon(Icons.person_add_outlined),
              title: Text('Users'),
              subtitle: Text('Create managers and change roles'),
              trailing: Icon(Icons.chevron_right),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
        ],
        AppCard(
          padding: const EdgeInsets.all(14),
          child: Row(
            children: [
              CircleAvatar(
                backgroundColor: AppColors.brandPrimaryDark,
                child: Text(
                  user.fullName.isEmpty ? '?' : user.fullName[0].toUpperCase(),
                  style: const TextStyle(color: AppColors.textOnBrand, fontWeight: FontWeight.w600),
                ),
              ),
              const SizedBox(width: AppSpacing.smMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(user.fullName, style: Theme.of(context).textTheme.titleMedium),
                    Text(
                      user.isOwner ? 'Owner' : 'Manager',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                  ],
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
                decoration: BoxDecoration(
                  color: AppColors.brandPrimarySoft,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text('You', style: Theme.of(context).textTheme.labelMedium?.copyWith(color: AppColors.brandPrimaryDeep, fontWeight: FontWeight.w600)),
              ),
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Text('DATA', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textSecondary)),
        const SizedBox(height: AppSpacing.sm),
        AppCard(
          onTap: () => context.pushNamed('reconciliation'),
          padding: EdgeInsets.zero,
          child: const ListTile(
            leading: Icon(Icons.balance_outlined),
            title: Text('Reconciliation'),
            subtitle: Text('Daily Revenue vs Cash Ledger'),
            trailing: Icon(Icons.chevron_right),
          ),
        ),
        const SizedBox(height: AppSpacing.sm),
        AppCard(
          onTap: () => context.pushNamed('audit'),
          padding: EdgeInsets.zero,
          child: const ListTile(
            leading: Icon(Icons.history),
            title: Text('Audit log'),
            subtitle: Text('What changed, and who changed it'),
            trailing: Icon(Icons.chevron_right),
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        Text('COMPANY', style: Theme.of(context).textTheme.labelLarge?.copyWith(color: AppColors.textSecondary)),
        const SizedBox(height: AppSpacing.sm),
        AppCard(
          padding: EdgeInsets.zero,
          child: Column(
            children: [
              const _CompanyRow(label: 'Currency', value: 'LKR'),
              const Divider(height: 1),
              const _CompanyRow(label: 'Time zone', value: 'Asia/Colombo'),
              const Divider(height: 1),
              const _CompanyRow(label: 'Day cut-off', value: '02:00'),
              if (canUseAi(user.role)) ...[
                const Divider(height: 1),
                const _CompanyRow(label: 'Assistant daily limit', value: r'$3.00'),
              ],
            ],
          ),
        ),
        const SizedBox(height: AppSpacing.md),
        OutlinedButton(
          onPressed: () => ref.read(authControllerProvider.notifier).logout(),
          style: OutlinedButton.styleFrom(foregroundColor: AppColors.error),
          child: const Text('Sign out'),
        ),
      ],
    );
  }
}

class _CompanyRow extends StatelessWidget {
  const _CompanyRow({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
      child: Row(
        children: [
          Expanded(child: Text(label, style: Theme.of(context).textTheme.bodyLarge)),
          Text(value, style: Theme.of(context).textTheme.bodyLarge?.copyWith(color: AppColors.textSecondary)),
        ],
      ),
    );
  }
}
