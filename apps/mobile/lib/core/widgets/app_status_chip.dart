import 'package:flutter/material.dart';

import '../theme/app_colors.dart';
import '../theme/app_spacing.dart';

enum AppStatusTone { neutral, success, warning, error, info }

/// Compact semantic chip (design.md §27). Colour is never the only signal —
/// the label always carries the meaning.
class AppStatusChip extends StatelessWidget {
  const AppStatusChip({
    super.key,
    required this.label,
    this.tone = AppStatusTone.neutral,
    this.icon,
  });

  final String label;
  final AppStatusTone tone;
  final IconData? icon;

  factory AppStatusChip.recordStatus(String status) {
    final upper = status.toUpperCase();
    return switch (upper) {
      'ACTIVE' => const AppStatusChip(label: 'Active', tone: AppStatusTone.success),
      'REVERSED' => const AppStatusChip(
        label: 'Reversed',
        tone: AppStatusTone.warning,
        icon: Icons.undo,
      ),
      'VOID' => const AppStatusChip(
        label: 'Void',
        tone: AppStatusTone.neutral,
        icon: Icons.block,
      ),
      'PENDING' => const AppStatusChip(
        label: 'Pending',
        tone: AppStatusTone.warning,
      ),
      'PAID' => const AppStatusChip(label: 'Paid', tone: AppStatusTone.success),
      _ => AppStatusChip(label: status, tone: AppStatusTone.neutral),
    };
  }

  factory AppStatusChip.reconciliation({required bool matches}) {
    return matches
        ? const AppStatusChip(
            label: 'Matched',
            tone: AppStatusTone.success,
            icon: Icons.check_circle_outline,
          )
        : const AppStatusChip(
            label: 'Difference',
            tone: AppStatusTone.warning,
            icon: Icons.warning_amber_rounded,
          );
  }

  @override
  Widget build(BuildContext context) {
    final (bg, fg) = switch (tone) {
      AppStatusTone.success => (AppColors.successSoft, AppColors.success),
      AppStatusTone.warning => (AppColors.warningSoft, AppColors.warning),
      AppStatusTone.error => (AppColors.errorSoft, AppColors.error),
      AppStatusTone.info => (AppColors.infoSoft, AppColors.info),
      AppStatusTone.neutral => (AppColors.surfaceSubtle, AppColors.textSecondary),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 14, color: fg),
            const SizedBox(width: 4),
          ],
          Text(
            label,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: fg,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}
