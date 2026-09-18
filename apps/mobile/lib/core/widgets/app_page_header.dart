import 'package:flutter/material.dart';

import '../theme/app_spacing.dart';

/// Screen/section header (design.md §16.1): title, optional context line,
/// trailing actions. One primary action belongs here or on the FAB, not both.
class AppPageHeader extends StatelessWidget {
  const AppPageHeader({
    super.key,
    required this.title,
    this.subtitle,
    this.actions,
  });

  final String title;
  final String? subtitle;
  final List<Widget>? actions;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.md,
        AppSpacing.sm,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: textTheme.headlineSmall),
                if (subtitle != null) ...[
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    subtitle!,
                    style: textTheme.bodySmall,
                  ),
                ],
              ],
            ),
          ),
          if (actions != null && actions!.isNotEmpty)
            Wrap(spacing: AppSpacing.sm, children: actions!),
        ],
      ),
    );
  }
}
